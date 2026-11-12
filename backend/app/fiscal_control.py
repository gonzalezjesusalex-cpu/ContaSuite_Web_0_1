"""Internal obligation tracking. Independent metadata: never auto-migrated at startup."""
from datetime import date, datetime
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (MetaData, Table, Column, String, Integer, Boolean, Date, DateTime, JSON,
                        ForeignKey, UniqueConstraint, CheckConstraint, Index, func, select, update, inspect)
from sqlalchemy.exc import IntegrityError
from .database import session
from .models import Company, UserAccount, Document, now
from .security import auth, Principal

metadata=MetaData()
catalog=Table('fiscal_catalog',metadata,Column('id',String(36),primary_key=True),
    Column('label',String(100),nullable=False),Column('periodicity',String(12),nullable=False),
    CheckConstraint("periodicity IN ('monthly','quarterly','annual')"))
Index('uq_fiscal_catalog_name',func.lower(catalog.c.label),unique=True)
applicability=Table('fiscal_applicability',metadata,
    Column('company_id',ForeignKey(Company.id),primary_key=True),
    Column('obligation_id',ForeignKey(catalog.c.id),primary_key=True),
    Column('applicable',Boolean,nullable=False),Column('responsible_id',ForeignKey(UserAccount.id)),
    Column('updated_at',DateTime(timezone=True),nullable=False),Column('revision',Integer,nullable=False))
periods=Table('fiscal_periods',metadata,Column('id',String(12),primary_key=True),
    Column('start_date',Date,nullable=False),Column('end_date',Date,nullable=False))
records=Table('fiscal_records',metadata,Column('id',String(36),primary_key=True),
    Column('company_id',ForeignKey(Company.id),nullable=False),Column('obligation_id',ForeignKey(catalog.c.id),nullable=False),
    Column('period_id',ForeignKey(periods.c.id),nullable=False),Column('status',String(20),nullable=False),
    Column('responsible_id',ForeignKey(UserAccount.id)),Column('registered_at',DateTime(timezone=True),nullable=False),
    Column('submitted_at',Date),Column('due_date',Date),Column('due_verified',Boolean,nullable=False),
    Column('payment',String(20),nullable=False),Column('notes',String(2000),nullable=False),
    Column('revision',Integer,nullable=False),Column('updated_at',DateTime(timezone=True),nullable=False),
    UniqueConstraint('company_id','obligation_id','period_id'),
    CheckConstraint("status IN ('fulfilled','pending','in_progress','not_applicable','unreviewed')"),
    CheckConstraint("payment IN ('unknown','pending','paid','not_applicable')"))
evidence=Table('fiscal_evidence',metadata,Column('record_id',ForeignKey(records.c.id),primary_key=True),
    Column('document_id',ForeignKey(Document.id),primary_key=True),Column('role',String(30),nullable=False))
history=Table('fiscal_history',metadata,Column('id',String(36),primary_key=True),
    Column('record_id',ForeignKey(records.c.id)),Column('company_id',ForeignKey(Company.id)),
    Column('actor_id',String(100),nullable=False),Column('created_at',DateTime(timezone=True),nullable=False),
    Column('before',JSON),Column('after',JSON,nullable=False))
imports=Table('fiscal_import_batches',metadata,Column('id',String(36),primary_key=True),
    Column('filename',String(255),nullable=False),Column('sha256',String(64),nullable=False),
    Column('actor_id',String(100),nullable=False),Column('created_at',DateTime(timezone=True),nullable=False),
    Column('status',String(20),nullable=False),Column('mapping',JSON,nullable=False))
import_rows=Table('fiscal_import_rows',metadata,Column('batch_id',ForeignKey(imports.c.id),primary_key=True),
    Column('sheet',String(100),primary_key=True),Column('row_number',Integer,primary_key=True),
    Column('original',JSON,nullable=False),Column('proposal',JSON),Column('conflicts',JSON,nullable=False))
INITIAL=['Contabilidad','ISR','IVA','Retenciones','DIOT','REPSE','Impuesto sobre Nómina','Nómina 1','Nómina 2','IMSS','Emisiones IMSS']
router=APIRouter(prefix='/api/fiscal-control',tags=['Control de obligaciones'])

def ready(db):
    if not all(inspect(db.connection()).has_table(t.name) for t in metadata.sorted_tables):
        raise HTTPException(503,'Control de obligaciones pendiente de migración autorizada. No se modificó la base.')

def period_key(year,month,frequency):
    return f'{year}-A' if frequency=='annual' else f'{year}-Q{(month-1)//3+1}' if frequency=='quarterly' else f'{year}-{month:02d}'

def effective(row,today=None):
    from .fiscal_read import cutoff
    if row and row['status'] in ('pending','in_progress') and row['due_verified'] and row['due_date'] and row['due_date']<(today or cutoff()):
        return 'overdue'
    return row['status'] if row else 'unreviewed'

def serial(row):
    return {k:v.isoformat() if isinstance(v,(date,datetime)) else v for k,v in dict(row).items()}

class EvidenceIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    document_id:str=Field(max_length=36)
    role:Literal['declaration','receipt','capture_line','payment','other']='other'

class CellIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    company_id:str=Field(max_length=36)
    obligation_id:str=Field(max_length=36)
    year:int=Field(ge=2000,le=2100)
    month:int=Field(ge=1,le=12)
    revision:int=Field(ge=0)
    status:Literal['fulfilled','pending','in_progress','not_applicable','unreviewed']='unreviewed'
    responsible_id:str|None=None
    submitted_at:date|None=None
    due_date:date|None=None
    due_verified:bool=False
    payment:Literal['unknown','pending','paid','not_applicable']='unknown'
    notes:str=Field('',max_length=2000)
    evidence:list[EvidenceIn]=Field(default_factory=list,max_length=20)
    @model_validator(mode='after')
    def valid(self):
        if self.due_verified and not self.due_date:raise ValueError('Captura la fecha límite verificada.')
        if len({e.document_id for e in self.evidence})!=len(self.evidence):raise ValueError('Documento repetido.')
        return self

@router.get('')
def matrix(year:int=Query(ge=2000,le=2100),month:int=Query(ge=1,le=12),principal:Principal=Depends(auth),db=Depends(session),company_id:str|None=None,regime:str|None=None,responsible:str|None=None,status:str|None=None,query:str|None=None,include_archived:bool=False):
    from .fiscal_read import read_period
    return read_period(db,principal,year,month,company_id,regime,responsible,status,query,include_archived)

def _matrix_data(year,month,principal,db):
    ready(db)
    companies=db.scalars(select(Company).order_by(Company.name)).all()
    companies=[c for c in companies if principal.admin or c.id in principal.company_ids]
    ids=[c.id for c in companies]
    definitions=[dict(r) for r in db.execute(select(catalog)).mappings()]
    keys=[period_key(year,month,f) for f in ['monthly','quarterly','annual']]
    entries=[]
    for row in db.execute(select(records).where(records.c.company_id.in_(ids),records.c.period_id.in_(keys))).mappings():
        item=serial(row);item['effective_status']=effective(row)
        item['evidence']=[dict(e) for e in db.execute(select(evidence.c.document_id,evidence.c.role).where(evidence.c.record_id==row['id'])).mappings()]
        entries.append(item)
    rules=[dict(r) for r in db.execute(select(applicability).where(applicability.c.company_id.in_(ids))).mappings()]
    assigned={r['responsible_id'] for r in entries+rules if r.get('responsible_id')}
    users_query=select(UserAccount.id,UserAccount.display_name).where(UserAccount.enabled==True)
    if not principal.admin:users_query=users_query.where(UserAccount.id.in_(assigned))
    users=[dict(r) for r in db.execute(users_query).mappings()]
    return dict(companies=[dict(id=c.id,name=c.name,rfc=c.rfc,regime=c.regime,accountant=c.accountant) for c in companies],catalog=definitions,records=entries,applicability=rules,users=users)

@router.put('/cell')
def save_cell(payload:CellIn,principal:Principal=Depends(auth),db=Depends(session)):
    ready(db);principal.require_company(payload.company_id,write=True)
    if not db.get(Company,payload.company_id):raise HTTPException(404,'Empresa no encontrada.')
    definition=db.execute(select(catalog).where(catalog.c.id==payload.obligation_id)).mappings().first()
    if not definition:raise HTTPException(404,'Obligación no encontrada.')
    if payload.responsible_id:
        user=db.get(UserAccount,payload.responsible_id)
        from .models import UserCompanyGrant
        if not user or not user.enabled or (not user.admin and not db.get(UserCompanyGrant,(user.id,payload.company_id))):raise HTTPException(422,'Responsable sin acceso a la empresa.')
    # Reuse CS-Storage authorization and company links; never open the source file.
    from .storage.router import storage_service
    for item in payload.evidence:
        from .storage.providers import StorageError
        try:
            document=storage_service().document(principal.storage_actor(),item.document_id)
        except StorageError:raise HTTPException(404,'Evidencia no disponible para esta cuenta.') from None
        if payload.company_id not in document.company_ids:raise HTTPException(422,'La evidencia debe estar vinculada a esta empresa.')
    key=period_key(payload.year,payload.month,definition['periodicity'])
    previous=db.execute(select(records).where(records.c.company_id==payload.company_id,records.c.obligation_id==payload.obligation_id,records.c.period_id==key)).mappings().first()
    if (previous['revision'] if previous else 0)!=payload.revision:raise HTTPException(409,'La celda cambió; actualiza antes de guardar.')
    ident=previous['id'] if previous else str(uuid4())
    data=payload.model_dump(exclude={'year','month','revision','evidence'})
    data.update(period_id=key,revision=payload.revision+1,updated_at=now())
    try:
        if previous:
            before=serial(previous)
            before['evidence']=[dict(e) for e in db.execute(select(evidence.c.document_id,evidence.c.role).where(evidence.c.record_id==ident)).mappings()]
            if not db.execute(update(records).where(records.c.id==ident,records.c.revision==payload.revision).values(**data)).rowcount:raise HTTPException(409,'Edición concurrente; actualiza.')
        else:
            before=None
            if not db.execute(select(periods.c.id).where(periods.c.id==key)).first():
                import calendar
                first=1 if definition['periodicity']=='annual' else ((payload.month-1)//3*3+1) if definition['periodicity']=='quarterly' else payload.month
                last=12 if definition['periodicity']=='annual' else first+2 if definition['periodicity']=='quarterly' else first
                db.execute(periods.insert().values(id=key,start_date=date(payload.year,first,1),end_date=date(payload.year,last,calendar.monthrange(payload.year,last)[1])))
            db.execute(records.insert().values(id=ident,registered_at=now(),**data))
        db.execute(evidence.delete().where(evidence.c.record_id==ident))
        for item in payload.evidence:db.execute(evidence.insert().values(record_id=ident,**item.model_dump()))
        after=serial(data);after['evidence']=[e.model_dump() for e in payload.evidence]
        db.execute(history.insert().values(id=str(uuid4()),record_id=ident,company_id=payload.company_id,actor_id=principal.subject,created_at=now(),before=before,after=after))
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Registro concurrente o relación inválida; actualiza.') from None
    return dict(id=ident,revision=payload.revision+1)

@router.get('/history/{record_id}')
def changes(record_id:str,principal:Principal=Depends(auth),db=Depends(session)):
    ready(db)
    row=db.execute(select(records).where(records.c.id==record_id)).mappings().first()
    if not row:raise HTTPException(404,'Registro no encontrado.')
    principal.require_company(row['company_id'])
    return [dict(r) for r in db.execute(select(history).where(history.c.record_id==record_id).order_by(history.c.created_at.desc()).limit(100)).mappings()]

class ApplicabilityIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    company_id:str=Field(max_length=36)
    obligation_id:str=Field(max_length=36)
    applicable:bool
    responsible_id:str|None=None
    revision:int=Field(ge=0)

@router.put('/applicability')
def save_applicability(payload:ApplicabilityIn,principal:Principal=Depends(auth),db=Depends(session)):
    ready(db);principal.require_company(payload.company_id,write=True)
    if not db.get(Company,payload.company_id) or not db.execute(select(catalog.c.id).where(catalog.c.id==payload.obligation_id)).first():raise HTTPException(404,'Empresa u obligación no encontrada.')
    if payload.responsible_id:
        from .models import UserCompanyGrant
        user=db.get(UserAccount,payload.responsible_id)
        if not user or not user.enabled or (not user.admin and not db.get(UserCompanyGrant,(user.id,payload.company_id))):raise HTTPException(422,'Responsable sin acceso a la empresa.')
    condition=(applicability.c.company_id==payload.company_id)&(applicability.c.obligation_id==payload.obligation_id)
    old=db.execute(select(applicability).where(condition)).mappings().first()
    if (old['revision'] if old else 0)!=payload.revision:raise HTTPException(409,'La aplicación cambió; actualiza.')
    data=payload.model_dump();data.update(revision=payload.revision+1,updated_at=now())
    try:
        if old:
            if not db.execute(update(applicability).where(condition,applicability.c.revision==payload.revision).values(**data)).rowcount:raise HTTPException(409,'Edición concurrente.')
        else:db.execute(applicability.insert().values(**data))
        db.execute(history.insert().values(id=str(uuid4()),company_id=payload.company_id,actor_id=principal.subject,created_at=now(),before=serial(old) if old else None,after={'action':'applicability',**serial(data)}))
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Configuración concurrente; actualiza.') from None
    return {'revision':payload.revision+1}

class CatalogIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    label:str=Field(min_length=1,max_length=100)
    periodicity:Literal['monthly','quarterly','annual']='monthly'

@router.post('/catalog',status_code=201)
def add_definition(payload:CatalogIn,principal:Principal=Depends(auth),db=Depends(session)):
    principal.require_admin();ready(db)
    if not payload.label.strip():raise HTTPException(422,'Nombre requerido.')
    if payload.label.strip().casefold()=='pago':raise HTTPException(422,'Pago se registra como atributo de una obligación.')
    existing=db.execute(select(catalog.c.label)).scalars()
    if any(s.casefold()==payload.label.strip().casefold() for s in existing):raise HTTPException(409,'Nombre de obligación ya registrado.')
    ident=str(uuid4())
    try:
        db.execute(catalog.insert().values(id=ident,label=payload.label.strip(),periodicity=payload.periodicity))
        db.execute(history.insert().values(id=str(uuid4()),actor_id=principal.subject,created_at=now(),after={'action':'catalog_created','id':ident,**payload.model_dump()}));db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Nombre de obligación ya registrado.') from None
    return {'id':ident}
