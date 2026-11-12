"""Bounded synthetic previews and audited decisions; final import deliberately disabled."""
import hashlib,json
from uuid import uuid4
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Request,Query
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select,inspect,update,delete,or_
from sqlalchemy.exc import IntegrityError
from .database import session
from .security import auth,Principal,utc
from .models import Company,Document,DocumentLocation,DocumentVersion,DocumentCompanyLink,now
from .company_import_models import metadata,sessions,rows,decisions,aliases,permissions,history
from .company_reconcile import reconcile,document_proposals
from .company_xlsx import read_xlsx,InvalidWorkbook

router=APIRouter(prefix='/api/company-imports',tags=['Importar y conciliar'])
def ready(db):
    if not all(inspect(db.connection()).has_table(t.name) for t in metadata.sorted_tables):raise HTTPException(503,'Importador pendiente de migración autorizada; no se modificaron datos.')
def visible(p,db):
    query=select(Company)
    if not p.admin:
        allowed_ids=select(permissions.c.company_id).where(permissions.c.user_id==p.subject)
        query=query.where(Company.id.in_(p.company_ids),Company.id.in_(allowed_ids))
    return [dict(id=c.id,name=c.name,rfc=c.rfc,regime=c.regime) for c in db.scalars(query.order_by(Company.id))]
def identity(p,db):
    ready(db)
    if p.bootstrap or not p.session_id:raise HTTPException(403,'Se requiere una sesión personal.')
    companies=visible(p,db)
    if not p.admin and not companies:raise HTTPException(403,'Sin permiso de importación para empresas.')
    return companies
def audit(db,p,ident,action,counts=None):
    db.execute(history.insert().values(id=str(uuid4()),session_id=ident,actor_id=p.subject,action=action,created_at=now(),counts=counts or {}))
def get_session(db,p,ident):
    identity(p,db)
    item=db.execute(select(sessions).where(sessions.c.id==ident)).mappings().first()
    if not item or item['owner_id']!=p.subject or item['source']=='local_pilot':raise HTTPException(404,'Sesión no disponible.')
    if utc(item['expires_at'])<=now():raise HTTPException(410,'La propuesta caducó; solicita su eliminación y vuelve a analizar.')
    return item
def summary(proposals):
    counts={}
    for row in proposals:
        kind=row.get('status',row.get('match','manual_review'));counts[kind]=counts.get(kind,0)+1
    return {'total':len(proposals),'states':counts,'confirmation_enabled':False,'secrets_import_enabled':False}
def save_preview(db,p,source,digest,proposals,details,companies,alternate_names=()):
    catalog_digest=hashlib.sha256(json.dumps({'companies':companies,'aliases':sorted(alternate_names,key=lambda a:(a['company_id'],a['name']))},sort_keys=True).encode()).hexdigest()
    key=hashlib.sha256(f'{p.subject}|{source}|{digest}|{catalog_digest}|v1'.encode()).hexdigest()
    old=db.execute(select(sessions.c.id).where(sessions.c.idempotency_key==key)).scalar()
    if old:return load(old,p,db)
    ident=str(uuid4());info={**summary(proposals),**details}
    try:
        db.execute(sessions.insert().values(id=ident,owner_id=p.subject,idempotency_key=key,source=source,source_sha256=digest,summary=info,created_at=now(),expires_at=now()+timedelta(hours=24),status='preview'))
        for number,proposal in enumerate(proposals,1):db.execute(rows.insert().values(session_id=ident,number=number,proposal=proposal,revision=0))
        audit(db,p,ident,'preview_created',{'rows':len(proposals)});db.commit()
    except IntegrityError:
        db.rollback();ident=db.execute(select(sessions.c.id).where(sessions.c.idempotency_key==key)).scalar()
        if not ident:raise HTTPException(409,'Conflicto de análisis; reintenta.') from None
    return load(ident,p,db)

@router.post('/preview/xlsx')
async def preview_xlsx(request:Request,source:Literal['obligations','fiscal_metadata'],synthetic_only:bool=False,p:Principal=Depends(auth),db=Depends(session)):
    companies=identity(p,db)
    if not synthetic_only:raise HTTPException(423,'Sólo está habilitado el análisis de archivos sintéticos en esta iteración.')
    # Raw octet stream avoids multipart spooling sensitive uploads to disk.
    payload=bytearray()
    async for chunk in request.stream():
        if len(payload)+len(chunk)>8*1024*1024:raise HTTPException(413,'Archivo superior a 8 MB.')
        payload.extend(chunk)
    digest=hashlib.sha256(payload).hexdigest()
    try:parsed=read_xlsx(bytes(payload),source)
    except InvalidWorkbook:raise HTTPException(422,'Archivo no admitido, corrupto o fuera de límites.') from None
    finally:payload.clear()
    alt=[{'company_id':r.company_id,'name':r.original_name} for r in db.execute(select(aliases).where(aliases.c.company_id.in_([c['id'] for c in companies])))]
    result=reconcile(parsed['rows'],companies,alt)
    return save_preview(db,p,source,digest,result,{'sheets':parsed['sheets'],'periods':sorted({s['period'] for s in parsed['sheets'] if s['period']})},companies,alt)

@router.post('/preview/inventory')
def inventory(p:Principal=Depends(auth),db=Depends(session)):
    companies=identity(p,db);ids=[c['id'] for c in companies]
    query=select(Document).where(or_(Document.name.ilike('%.pdf'),Document.name.ilike('%.xml'),Document.name.ilike('%.cer')))
    if not p.admin:query=query.where(or_(Document.company_id.in_(ids),Document.id.in_(select(DocumentCompanyLink.document_id).where(DocumentCompanyLink.company_id.in_(ids)))))
    documents=list(db.scalars(query.order_by(Document.id).limit(501)))
    if len(documents)>500:raise HTTPException(413,'Inventario mayor a 500 documentos; usar un piloto más acotado.')
    observed=[]
    for doc in documents:
        locations=list(db.scalars(select(DocumentLocation.relative_key).join(DocumentVersion,DocumentLocation.version_id==DocumentVersion.id).where(DocumentVersion.document_id==doc.id,DocumentVersion.number==doc.storage_revision).limit(10)))
        linked=list(db.scalars(select(DocumentCompanyLink.company_id).where(DocumentCompanyLink.document_id==doc.id)))
        observed.append(dict(id=doc.id,name=doc.name,path=' '.join(locations),period=doc.period,linked_company_ids=sorted(set(linked+([doc.company_id] if doc.company_id else [])))))
    alt=[{'company_id':r.company_id,'name':r.original_name} for r in db.execute(select(aliases)) if r.company_id in ids]
    proposals=document_proposals(observed,companies,alt)
    digest=hashlib.sha256(json.dumps(observed,sort_keys=True).encode()).hexdigest()
    return save_preview(db,p,'inventory',digest,proposals,{'incremental_reindex_enabled':False},companies,alt)

@router.get('/{ident}')
def load(ident:str,p:Principal=Depends(auth),db=Depends(session)):
    item=get_session(db,p,ident);allowed_ids={c['id'] for c in visible(p,db)};items=[]
    for row in db.execute(select(rows).where(rows.c.session_id==ident).order_by(rows.c.number)).mappings():
        value=dict(row['proposal'])
        # Recheck grants at each read; do not leak stale suggestions after revocation.
        value['candidates']=[c for c in value.get('candidates',[]) if c['company_id'] in allowed_ids]
        value['company_ids']=[c for c in value.get('company_ids',[]) if c in allowed_ids]
        if value.get('decision_company_id') not in allowed_ids:value['decision_company_id']=None
        if value.get('alias_proposal',{}).get('company_id') not in allowed_ids:value.pop('alias_proposal',None)
        if not p.admin:value['rfc']='••••'+value.get('rfc','')[-3:] if value.get('rfc') else ''
        items.append({'number':row['number'],'revision':row['revision'],**value})
    return {'id':ident,'source':item['source'],'expires_at':item['expires_at'],'summary':item['summary'],'rows':items,'confirmation_enabled':False}

class DecisionIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=0)
    action:Literal['link','create','exclude','pending']
    company_id:str|None=Field(None,max_length=36)

@router.put('/{ident}/rows/{number}')
def decide(ident:str,number:int,payload:DecisionIn,p:Principal=Depends(auth),db=Depends(session)):
    get_session(db,p,ident);allowed_ids={c['id'] for c in visible(p,db)}
    if payload.action=='link' and payload.company_id not in allowed_ids:raise HTTPException(403,'Empresa fuera del ámbito autorizado.')
    if payload.action=='create' and not p.admin:raise HTTPException(403,'Proponer nuevas empresas requiere administración.')
    row=db.execute(select(rows).where(rows.c.session_id==ident,rows.c.number==number)).mappings().first()
    if not row:raise HTTPException(404,'Registro no encontrado.')
    if row['revision']!=payload.revision:raise HTTPException(409,'La propuesta cambió; actualiza.')
    proposal=dict(row['proposal'])
    if payload.action=='create' and not proposal.get('format_valid'):raise HTTPException(422,'RFC con formato válido requerido antes de proponer alta.')
    proposal.update(action=payload.action,decision_company_id=payload.company_id if payload.action=='link' else None)
    if payload.action=='link' and proposal.get('name'):
        proposal['alias_proposal']={'original_name':proposal['name'],'company_id':payload.company_id,'requires_final_confirmation':True}
    if not db.execute(update(rows).where(rows.c.session_id==ident,rows.c.number==number,rows.c.revision==payload.revision).values(proposal=proposal,revision=payload.revision+1)).rowcount:raise HTTPException(409,'Edición concurrente.')
    db.execute(decisions.insert().values(id=str(uuid4()),session_id=ident,row_number=number,actor_id=p.subject,action=payload.action,company_id=payload.company_id if payload.action=='link' else None,created_at=now(),revision=payload.revision+1))
    audit(db,p,ident,'decision_saved',{'row':number,'revision':payload.revision+1});db.commit()
    return {'saved':True,'applied_to_companies':False,'revision':payload.revision+1}

class ConfirmIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirmed:bool
@router.post('/{ident}/confirm')
def confirm(ident:str,payload:ConfirmIn,p:Principal=Depends(auth),db=Depends(session)):
    get_session(db,p,ident)
    if not payload.confirmed:raise HTTPException(422,'Confirmación explícita requerida.')
    audit(db,p,ident,'confirmation_blocked');db.commit()
    raise HTTPException(423,'Aplicación definitiva deshabilitada hasta aprobar pruebas y migraciones.')

@router.get('/{ident}/report')
def report(ident:str,p:Principal=Depends(auth),db=Depends(session)):
    item=get_session(db,p,ident)
    totals={}
    for proposal in db.scalars(select(rows.c.proposal).where(rows.c.session_id==ident)):
        key=proposal.get('action','pending');totals[key]=totals.get(key,0)+1
    return {'id':ident,'summary':item['summary'],'decisions':totals,'applied':False,'secrets_imported':0}

@router.delete('/{ident}')
def discard(ident:str,p:Principal=Depends(auth),db=Depends(session)):
    identity(p,db)
    item=db.execute(select(sessions).where(sessions.c.id==ident,sessions.c.owner_id==p.subject)).mappings().first()
    if not item or item['source']=='local_pilot':raise HTTPException(404,'Sesión no disponible.')
    # No source files were retained; erase staging rows, keep aggregate audit only.
    db.execute(delete(decisions).where(decisions.c.session_id==ident));db.execute(delete(rows).where(rows.c.session_id==ident))
    db.execute(delete(sessions).where(sessions.c.id==ident));audit(db,p,ident,'preview_discarded');db.commit()
    return {'deleted':True,'original_files_affected':False}

@router.delete('/maintenance/expired')
def purge_expired(p:Principal=Depends(auth),db=Depends(session)):
    identity(p,db);p.require_admin()
    expired=list(db.scalars(select(sessions.c.id).where(sessions.c.expires_at<=now(),sessions.c.source!='local_pilot')))
    if expired:
        db.execute(delete(decisions).where(decisions.c.session_id.in_(expired)))
        db.execute(delete(rows).where(rows.c.session_id.in_(expired)))
        db.execute(delete(sessions).where(sessions.c.id.in_(expired)))
    audit(db,p,None,'expired_previews_purged',{'sessions':len(expired)});db.commit()
    return {'purged':len(expired),'source_files_stored':False}
