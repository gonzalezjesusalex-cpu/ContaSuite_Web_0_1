"""Recibos web: conserva las reglas y el PDF del motor de escritorio."""
import io
import zipfile
from datetime import date
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text, or_, update
from sqlalchemy.orm import Session
from .database import session, DATA
from .models import Company, Receipt, ReceiptCounter, Setting, Audit, ReceiptClient
from . import receipt_engine as motor

router = APIRouter(prefix='/api/receipts', tags=['Recibos'])

class Item(BaseModel):
    company_id: str | None = None
    client_id: str | None = None
    name: str = Field(default='', max_length=220)
    concept: str = Field(default='', max_length=500)
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=1900, le=2100)
    amount: str
    issued: date

class Batch(BaseModel):
    items: list[Item] = Field(min_length=1, max_length=300)
    allow_duplicates: bool = False

class Settings(BaseModel):
    receiver: str = Field(min_length=1, max_length=180)
    place: str = Field(min_length=1, max_length=180)

class Selection(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=300)
    format: str = 'pdf'

def settings(db):
    return {k: (db.get(Setting, 'receipts_'+k).value if db.get(Setting, 'receipts_'+k) else v) for k,v in motor.DEFAULTS.items()}

def validated(db, item):
    name=item.name
    if item.company_id:
        company=db.get(Company,item.company_id)
        if not company:raise HTTPException(404,'Empresa no encontrada')
        name=company.name
    elif item.client_id:
        client=db.get(ReceiptClient,item.client_id)
        if client:name=client.name
        elif not name:raise HTTPException(404,'Cliente no encontrado')
    try:
        d=motor.validate(dict(name=name,concept=item.concept,month=item.month,year=item.year,amount=item.amount,issued=item.issued.isoformat()))
        return d
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc

def duplicates(db, items):
    seen=set();found=[]
    for item in items:
        d=validated(db,item);key=(d['name'],item.year,item.month)
        identity=(Receipt.name==d['name'])
        if item.company_id:identity=or_(identity,Receipt.company_id==item.company_id)
        exists=db.scalar(select(Receipt.id).where(identity,Receipt.year==item.year,Receipt.month==item.month).limit(1))
        if key in seen or exists:found.append({'name':d['name'],'year':item.year,'month':item.month})
        seen.add(key)
    return found

class ClientIn(BaseModel):
    name: str = Field(min_length=1,max_length=220)

@router.get('/clients')
def clients(db: Session=Depends(session)):
    return db.scalars(select(ReceiptClient).order_by(ReceiptClient.name)).all()

@router.post('/clients',status_code=201)
def add_client(data: ClientIn, db: Session=Depends(session)):
    name=' '.join(data.name.split()).upper()
    if not name:raise HTTPException(422,'Escribe el nombre del cliente.')
    from sqlalchemy.exc import IntegrityError
    client=ReceiptClient(id=str(uuid4()),name=name,normalized_name=name)
    db.add(client)
    try:db.commit()
    except IntegrityError:
        db.rollback()
        return db.scalar(select(ReceiptClient).where(ReceiptClient.normalized_name==name))
    return client

@router.delete('/clients/{ident}',status_code=204)
def remove_client(ident: str, db: Session=Depends(session)):
    client=db.get(ReceiptClient,ident)
    if not client:raise HTTPException(404,'Cliente no encontrado')
    # Snapshot name/concept/PDF remain untouched in the issued receipts.
    db.execute(update(Receipt).where(Receipt.client_id==ident).values(client_id=None))
    db.delete(client);db.commit()

@router.get('/settings')
def get_settings(db: Session=Depends(session)): return settings(db)

@router.put('/settings')
def put_settings(data: Settings, db: Session=Depends(session)):
    values={k:v.strip() for k,v in data.model_dump().items()}
    if not all(values.values()):raise HTTPException(422,'Completa el nombre de quien recibe y el lugar.')
    for k,v in values.items():db.merge(Setting(key='receipts_'+k,value=v))
    db.commit();return values

@router.post('/preview')
def preview(item: Item, db: Session=Depends(session)):
    d=validated(db,item)
    return Response(motor.receipt_pdf(d,settings(db)),media_type='application/pdf',headers={'Cache-Control':'no-store'})

@router.post('/duplicates')
def check_duplicates(data: Batch, db: Session=Depends(session)):
    for item in data.items:validated(db,item)
    return duplicates(db,data.items)

@router.get('')
def history(company_id: str | None=None, q: str='', year: int | None=None, db: Session=Depends(session)):
    query=select(Receipt).order_by(Receipt.created_at.desc(),Receipt.folio.desc())
    if company_id:query=query.where(Receipt.company_id==company_id)
    if year:query=query.where(Receipt.year==year)
    rows=db.scalars(query).all()
    # Literal matching: '%' and '_' have no wildcard meaning.
    return [r for r in rows if q.casefold() in f'{r.name} {r.folio} {r.year}-{r.month:02d} {r.issued} {r.amount} {r.concept}'.casefold()]

@router.post('',status_code=201)
def generate(data: Batch, db: Session=Depends(session)):
    # Serialize duplicate checks and issuance, including concurrent browser sessions.
    if db.bind.dialect.name=='sqlite':
        db.execute(text('BEGIN IMMEDIATE'))
    else:
        db.execute(text('SELECT pg_advisory_xact_lock(74328219)'))
    prepared=[validated(db,item) for item in data.items]
    if not data.allow_duplicates:
        found=duplicates(db,data.items)
        if found:raise HTTPException(409,{'message':'Ya hay recibos para estos contribuyentes y periodos. Confirma si deseas emitir otros.', 'duplicates':found})
    cfg=settings(db);folder=DATA/'receipts';folder.mkdir(exist_ok=True)
    created=[];rows=[]
    try:
        for item,d in zip(data.items,prepared):
            # Atomic annual counter works across processes in both supported databases.
            if db.bind.dialect.name=='postgresql':
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            stmt=insert(ReceiptCounter).values(year=item.issued.year,seq=1)
            seq=db.scalar(stmt.on_conflict_do_update(index_elements=['year'],set_={'seq':ReceiptCounter.seq+1}).returning(ReceiptCounter.seq))
            folio=f'{item.issued.year}-{seq:04d}';d['folio']=folio
            ident=str(uuid4());path=folder/(ident+'.pdf')
            payload=motor.receipt_pdf(d,cfg)
            with path.open('xb') as f:
                created.append(path);f.write(payload)
            filename=f"RECIBO_{folio}_{motor.slug(d['name'])}_{d['year']}-{d['month']:02d}.pdf"
            row=Receipt(id=ident,company_id=item.company_id or None,client_id=item.client_id if item.client_id and db.get(ReceiptClient,item.client_id) else None,folio=folio,filename=filename,storage_name=path.name,receiver=cfg['receiver'],place=cfg['place'],**d_without_folio(d))
            db.add(row);rows.append(row)
            db.add(Audit(company_id=item.company_id,action='Recibo emitido: '+folio))
        db.commit()
        return rows
    except Exception:
        db.rollback()
        for path in created:path.unlink(missing_ok=True)
        raise

def d_without_folio(d):return {k:v for k,v in d.items() if k!='folio'}

def receipt_file(db, ident):
    r=db.get(Receipt,ident)
    if not r:raise HTTPException(404,'Recibo no encontrado')
    path=DATA/'receipts'/r.storage_name
    if not path.is_file():raise HTTPException(404,'El PDF original no está disponible. Revisa el respaldo de los documentos.')
    return r,path

@router.get('/{ident}/pdf')
def pdf(ident: str, db: Session=Depends(session)):
    r,path=receipt_file(db,ident)
    return Response(path.read_bytes(),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{r.filename}"','Cache-Control':'no-store'})

@router.post('/export')
def export(data: Selection, db: Session=Depends(session)):
    if data.format not in ('pdf','zip'):raise HTTPException(422,'Elige PDF o ZIP.')
    files=[receipt_file(db,i) for i in dict.fromkeys(data.ids)]
    out=io.BytesIO()
    if data.format=='zip':
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for r,path in files:z.write(path,r.filename)
        media='application/zip';filename='RECIBOS.zip'
    else:
        from pypdf import PdfWriter
        with PdfWriter() as writer:
            for _,path in files:writer.append(str(path))
            writer.write(out)
        media='application/pdf';filename='RECIBOS_COMBINADOS.pdf'
    return Response(out.getvalue(),media_type=media,headers={'Content-Disposition':f'attachment; filename="{filename}"','Cache-Control':'no-store'})
