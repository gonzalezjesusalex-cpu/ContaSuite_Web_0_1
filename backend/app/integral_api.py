from datetime import date
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,model_validator
from sqlalchemy import select,update,inspect
from sqlalchemy.exc import IntegrityError
from .database import session
from .security import auth,Principal
from .models import Company,Document,DocumentVersion,DocumentLocation,DocumentCompanyLink,DocumentClassificationReview as Review,now
from .storage.catalog import DocumentCatalog
from .integral_models import metadata,categories,rules,classified,relations,verification,activity,audit,opinions,cfdi_reviews,quality
from .integral_dashboard import dashboard,exists
from .virtual_classifier import propose

router=APIRouter(prefix='/api/integral',tags=['Dashboard integral v0.3'])
def ready(db):
    if not all(inspect(db.connection()).has_table(t.name) for t in metadata.sorted_tables):raise HTTPException(503,'Dashboard integral pendiente de migración autorizada.')
def event(db,p,action,reference=None,cid=None,details=None):db.execute(audit.insert().values(id=str(uuid4()),company_id=cid,actor_id=p.subject,action=action,reference=reference,created_at=now(),details=details or {}))
def document(db,p,ident):
    doc=db.scalar(select(Document).where(Document.id==ident,DocumentCatalog()._scope(p.storage_actor())))
    if not doc or not doc.name.lower().endswith(('.pdf','.xml','.cer','.xlsx')):raise HTTPException(404,'Documento no disponible.')
    return doc
def version(db,doc):
    v=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==doc.id,DocumentVersion.number==doc.storage_revision))
    if not v:raise HTTPException(409,'Documento pendiente de versión verificada.')
    return v
def linked(db,doc):return set(db.scalars(select(DocumentCompanyLink.company_id).where(DocumentCompanyLink.document_id==doc.id)))|({doc.company_id} if doc.company_id else set())

@router.get('/dashboard')
def report(year:int=Query(ge=2000,le=2100),month:int=Query(ge=1,le=12),company_id:str|None=None,regime:str|None=None,responsible:str|None=None,include_archived:bool=False,p:Principal=Depends(auth),db=Depends(session)):
    ready(db)
    if company_id:p.require_company(company_id)
    return dashboard(db,p,year,month,company_id,regime,responsible,include_archived)

class ActiveIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    active:bool
@router.put('/companies/{cid}/activity')
def company_activity(cid:str,payload:ActiveIn,p:Principal=Depends(auth),db=Depends(session)):
    ready(db);p.require_admin()
    if not db.get(Company,cid):raise HTTPException(404,'Empresa no encontrada.')
    values=dict(company_id=cid,active=payload.active,actor_id=p.subject,updated_at=now())
    if db.execute(select(activity.c.company_id).where(activity.c.company_id==cid)).first():db.execute(update(activity).where(activity.c.company_id==cid).values(**values))
    else:db.execute(activity.insert().values(**values))
    event(db,p,'activity_confirmed',cid,cid);db.commit();return {'saved':True}

@router.get('/companies/{cid}/documents')
def explorer(cid:str,original:bool=False,offset:int=Query(0,ge=0),p:Principal=Depends(auth),db=Depends(session)):
    ready(db);p.require_company(cid)
    docs=db.scalars(select(Document).where(DocumentCatalog()._scope(p.storage_actor()),(Document.company_id==cid)|(Document.id.in_(select(DocumentCompanyLink.document_id).where(DocumentCompanyLink.company_id==cid)))).order_by(Document.id).offset(offset).limit(101)).all()
    result=[]
    for doc in docs[:100]:
        if doc.name.lower().endswith(('.key','.pfx','.p12','.pem')):continue
        v=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==doc.id,DocumentVersion.number==doc.storage_revision))
        info=db.execute(select(classified).where(classified.c.document_id==doc.id,classified.c.version_id==v.id)).mappings().first() if v else None
        item=dict(id=doc.id,name=doc.name,type=doc.document_type,revision=doc.storage_revision,classification=dict(info) if info else None,relative_paths=None,modification_ns=None)
        if original and p.admin and v:
            locations=db.scalars(select(DocumentLocation).where(DocumentLocation.version_id==v.id)).all()
            # Root/UNC locations and private key references are never exposed.
            from .storage.paths import safe_key
            paths=[]
            for loc in locations:
                try:paths.append(safe_key(loc.relative_key))
                except Exception:pass
            item['relative_paths']=paths;item['modification_ns']=[loc.mtime_ns for loc in locations]
        result.append(item)
    if original:event(db,p,'original_structure_viewed',cid,cid);db.commit()
    return {'documents':result,'more':len(docs)>100,'offset':offset,'paths_authorized':p.admin,'categories':[dict(r) for r in db.execute(select(categories)).mappings()]}

class AnalyzeIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    document_ids:list[str]=Field(min_length=1,max_length=50)
    reopen:bool=False
@router.post('/classification/analyze')
def analyze(payload:AnalyzeIn,p:Principal=Depends(auth),db=Depends(session)):
    ready(db);p.require_admin();result=[]
    companies=[dict(id=c.id,name=c.name,rfc=c.rfc) for c in db.scalars(select(Company))]
    rule_list=[dict(r) for r in db.execute(select(rules)).mappings()]
    aliases=[]
    if exists(db,'company_import_aliases'):
        from .company_import_models import aliases as alias_table
        aliases=[dict(company_id=r.company_id,name=r.original_name) for r in db.execute(select(alias_table))]
    for ident in sorted(set(payload.document_ids)):
        doc=document(db,p,ident);v=version(db,doc)
        from .document_identity import blocked
        if blocked(db,v.id):
            pending=db.scalar(select(Review).where(Review.version_id==v.id,Review.status=='pending').order_by(Review.created_at.desc()))
            result.append({'document_id':doc.id,'review_id':pending.id if pending else None,'preserved':True,'reason':'identity_review_required'});continue
        locations=list(db.scalars(select(DocumentLocation.relative_key).where(DocumentLocation.version_id==v.id).limit(10)))
        proposal=propose(dict(id=doc.id,name=doc.name,path=' '.join(locations),period=doc.period,linked_company_ids=sorted(linked(db,doc))),companies,rule_list,aliases)
        previous=db.scalar(select(Review).where(Review.version_id==v.id).order_by(Review.created_at.desc()))
        if previous and ((previous.evidence.get('origin')=='metadata_rules_v3' and previous.status=='pending') or (previous.status=='resolved' and not payload.reopen)):
            result.append({'document_id':doc.id,'review_id':previous.id,'preserved':True});continue
        review=Review(document_id=doc.id,version_id=v.id,status='pending',evidence=proposal,proposed_links=[{'company_id':cid,'role':'owner'} for cid in proposal.get('company_ids',[])])
        db.add(review);db.flush();result.append({'document_id':doc.id,'review_id':review.id,'proposal':proposal})
    event(db,p,'classification_proposed',details={'documents':len(result)});db.commit();return {'results':result,'source_files_opened':False}

@router.get('/classification/reviews')
def reviews(company_id:str|None=None,p:Principal=Depends(auth),db=Depends(session)):
    ready(db);p.require_admin()
    query=select(Review).where(Review.status=='pending').order_by(Review.created_at.desc()).limit(200)
    result=[]
    for row in db.scalars(query):
        if row.evidence.get('origin')!='metadata_rules_v3':continue
        if company_id and company_id not in {l['company_id'] for l in row.proposed_links}:continue
        result.append(dict(id=row.id,document_id=row.document_id,version_id=row.version_id,evidence=row.evidence))
    return result

class DecisionIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    review_id:str=Field(max_length=36)
    revision:int=Field(ge=1)
    action:Literal['confirm','reject']
    company_id:str=Field(max_length=36)
    category_id:str=Field(max_length=36)
    tags:list[str]=Field(default_factory=list,max_length=10)
    year:int|None=Field(None,ge=2000,le=2100)
    period:str|None=Field(None,pattern=r'^20\d{2}-(0[1-9]|1[0-2])$')
    obligation_id:str|None=Field(None,max_length=36)
    certificate_id:str|None=Field(None,max_length=36)
    reason:str=Field(min_length=3,max_length=1000)
    @model_validator(mode='after')
    def validate_period(self):
        if self.period and self.year and int(self.period[:4])!=self.year:raise ValueError('Ejercicio y período no coinciden.')
        if any(len(t)>60 or not t.strip() for t in self.tags):raise ValueError('Etiqueta inválida.')
        return self

@router.post('/classification/documents/{ident}/decision')
def decision(ident:str,payload:DecisionIn,p:Principal=Depends(auth),db=Depends(session)):
    ready(db);p.require_admin();p.require_company(payload.company_id,write=True)
    from .document_identity import lock,blocked
    lock(db)
    doc=document(db,p,ident);v=version(db,doc);review=db.get(Review,payload.review_id)
    if blocked(db,v.id):raise HTTPException(409,'Resuelve el conflicto de identidad en la revisión documental antes de clasificar metadatos.')
    if not review or review.document_id!=ident or review.version_id!=v.id or review.status!='pending' or payload.revision!=doc.storage_revision:raise HTTPException(409,'Versión o revisión cambiada; actualiza.')
    if not db.get(Company,payload.company_id) or not db.execute(select(categories.c.id).where(categories.c.id==payload.category_id)).first():raise HTTPException(422,'Empresa o categoría inválida.')
    if payload.action=='confirm':
        if payload.obligation_id:
            if not exists(db,'fiscal_records'):raise HTTPException(409,'Control de obligaciones no activado.')
            from .fiscal_control import records
            r=db.execute(select(records).where(records.c.id==payload.obligation_id)).mappings().first()
            if not r or r['company_id']!=payload.company_id or not payload.period or r['period_id']!=payload.period:raise HTTPException(422,'Empresa/período no coincide con la obligación. Períodos anuales requieren revisión específica.')
        if payload.certificate_id:
            if not exists(db,'vault_certificates'):raise HTTPException(409,'Certificados no activados.')
            from .credential_models import certificates
            cert=db.execute(select(certificates).where(certificates.c.id==payload.certificate_id)).mappings().first()
            if not cert or cert['company_id']!=payload.company_id:raise HTTPException(422,'Certificado de otra empresa.')
        if not db.execute(update(Document).where(Document.id==ident,Document.storage_revision==payload.revision).values(classification_status='confirmed')).rowcount:raise HTTPException(409,'Documento cambiado.')
        data=dict(document_id=ident,version_id=v.id,company_id=payload.company_id,category_id=payload.category_id,tags=sorted(set(payload.tags)),year=payload.year,period=payload.period,actor_id=p.subject,reviewed_at=now())
        previous=db.execute(select(classified).where(classified.c.document_id==ident,classified.c.version_id==v.id)).mappings().first()
        if previous:db.execute(update(classified).where(classified.c.document_id==ident,classified.c.version_id==v.id).values(**data,revision=previous['revision']+1))
        else:db.execute(classified.insert().values(**data,revision=1))
        if payload.company_id not in linked(db,doc):db.add(DocumentCompanyLink(document_id=ident,company_id=payload.company_id,role='owner',method='manual',confirmed_by=p.subject))
        for kind,target in [('obligation',payload.obligation_id),('certificate',payload.certificate_id)]:
            if target and not db.execute(select(relations.c.id).where(relations.c.version_id==v.id,relations.c.target_type==kind,relations.c.target_id==target)).first():db.execute(relations.insert().values(id=str(uuid4()),document_id=ident,version_id=v.id,company_id=payload.company_id,target_type=kind,target_id=target,actor_id=p.subject,created_at=now()))
    changed=db.execute(update(Review).where(Review.id==review.id,Review.status=='pending').values(status='resolved',resolution=payload.action,resolved_by=p.subject,resolved_at=now()))
    if not changed.rowcount:db.rollback();raise HTTPException(409,'Decisión concurrente.')
    event(db,p,'classification_'+payload.action,ident,payload.company_id,{'review_id':review.id,'reason':payload.reason,'category_id':payload.category_id,'period':payload.period})
    db.commit();return {'saved':True,'obligation_status_changed':False,'source_files_modified':False}

@router.get('/documents/{ident}/history')
def document_history(ident:str,p:Principal=Depends(auth),db=Depends(session)):
    ready(db);document(db,p,ident)
    return [dict(r) for r in db.execute(select(audit).where(audit.c.reference==ident,audit.c.company_id.in_(p.company_ids) if not p.admin else True).order_by(audit.c.created_at.desc()).limit(100)).mappings()]

class OpinionIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    authority:Literal['SAT','IMSS','INFONAVIT']
    consulted_on:date
    result:Literal['positive','negative','unreviewed','unavailable']='unreviewed'
    next_review:date|None=None
    document_id:str|None=None
    responsible:str=Field('',max_length=100)
    notes:str=Field('',max_length=2000)
@router.post('/companies/{cid}/opinions')
def add_opinion(cid:str,payload:OpinionIn,p:Principal=Depends(auth),db=Depends(session)):
    ready(db);p.require_company(cid,write=True)
    if not db.get(Company,cid):raise HTTPException(404,'Empresa no encontrada.')
    if payload.document_id and cid not in linked(db,document(db,p,payload.document_id)):raise HTTPException(422,'Documento de otra empresa.')
    ident=str(uuid4());db.execute(opinions.insert().values(id=ident,company_id=cid,**payload.model_dump(),actor_id=p.subject,created_at=now()));event(db,p,'opinion_registered',ident,cid);db.commit();return {'id':ident,'official_query_performed':False}

class CfdiIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    period:str=Field(pattern=r'^20\d{2}-(0[1-9]|1[0-2])$')
    kind:Literal['issued','received','payroll']
    reviewed_on:date
    state:Literal['pending','in_progress','reviewed']
    incidents:str=Field('',max_length=2000)
    responsible:str=Field('',max_length=100)
@router.post('/companies/{cid}/cfdi')
def add_cfdi(cid:str,payload:CfdiIn,p:Principal=Depends(auth),db=Depends(session)):
    ready(db);p.require_company(cid,write=True)
    if not db.get(Company,cid):raise HTTPException(404,'Empresa no encontrada.')
    ident=str(uuid4())
    try:db.execute(cfdi_reviews.insert().values(id=ident,company_id=cid,actor_id=p.subject,**payload.model_dump()));event(db,p,'cfdi_review_registered',ident,cid);db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,'Revisión ya registrada.') from None
    return {'id':ident,'sat_validated':False}

class VerifyIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    document_id:str
@router.post('/obligations/{ident}/verify')
def verify(ident:str,payload:VerifyIn,p:Principal=Depends(auth),db=Depends(session)):
    ready(db);p.require_admin()
    if not exists(db,'fiscal_records'):raise HTTPException(409,'Obligaciones no activadas.')
    from .fiscal_control import records
    from .evidence_history import record_verification
    from .lote4_lifecycle import invoke
    def operation():
        result=record_verification(db,p,ident,payload.revision,payload.document_id)
        if not result['idempotent']:
            cid=db.scalar(select(records.c.company_id).where(records.c.id==ident))
            event(db,p,'compliance_evidence_verified',ident,cid=cid,details={'decision_id':result['decision_id']})
        db.commit();return result
    return invoke(db,operation)

@router.get('/obligations/{ident}/verifications')
def verification_history(ident:str,p:Principal=Depends(auth),db=Depends(session)):
    from .evidence_history import ready as history_ready,decisions
    from .fiscal_control import records
    history_ready(db)
    row=db.execute(select(records).where(records.c.id==ident)).mappings().first()
    if not row:raise HTTPException(404,'Registro no encontrado.')
    p.require_company(row['company_id'])
    return [dict(r) for r in db.execute(select(decisions).where(decisions.c.record_id==ident).order_by(decisions.c.verified_at,decisions.c.id)).mappings()]


class CategoryIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    label:str=Field(min_length=1,max_length=100)
    terms:list[str]=Field(default_factory=list,max_length=20)
@router.post('/classification/categories')
def add_category(payload:CategoryIn,p:Principal=Depends(auth),db=Depends(session)):
    ready(db);p.require_admin()
    if not payload.label.strip() or any(not t.strip() or len(t)>60 for t in payload.terms):raise HTTPException(422,'Nombre o términos inválidos.')
    ident=str(uuid4())
    try:
        db.execute(categories.insert().values(id=ident,label=payload.label.strip()))
        if payload.terms:db.execute(rules.insert().values(id=ident,category_id=ident,terms=payload.terms,enabled=True))
        event(db,p,'category_created',ident);db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,'Categoría ya registrada.') from None
    return {'id':ident}

class CompareIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    document_id:str=Field(max_length=36)
@router.post('/certificates/{ident}/compare')
def compare_certificate(ident:str,payload:CompareIn,p:Principal=Depends(auth),db=Depends(session)):
    ready(db)
    if not exists(db,'vault_certificates'):raise HTTPException(409,'Certificados no activados.')
    from .credential_models import certificates
    from .credential_api import allowed,parse_public_certificate
    from .security import utc
    row=db.execute(select(certificates).where(certificates.c.id==ident)).mappings().first()
    if not row:raise HTTPException(404,'Certificado no encontrado.')
    allowed(p,db,row['company_id'],'certificates')
    doc=document(db,p,payload.document_id)
    if row['company_id'] not in linked(db,doc) or not doc.name.lower().endswith('.cer'):raise HTTPException(422,'CER público de otra empresa o formato no admitido.')
    from .storage.router import storage_service
    from .storage.providers import StorageError
    try:
        with storage_service().read(p.storage_actor(),doc.id) as content:parsed=parse_public_certificate(content.stream.read(1024*1024+1))
    except StorageError:raise HTTPException(409,'No se pudo leer el certificado público.') from None
    conflicts=[key for key in ('valid_from','valid_until') if row[key] and utc(row[key])!=parsed[key]]
    if row['fingerprint'] and row['fingerprint']!=parsed['fingerprint']:conflicts.append('fingerprint')
    import hashlib
    key=hashlib.sha256(('certificate_mismatch:'+ident).encode()).hexdigest()
    values=dict(company_id=row['company_id'],source='certificate',reference=ident,code='certificate_dates_or_identity_mismatch',state='open' if conflicts else 'resolved',provenance={'document_id':doc.id,'fields':conflicts})
    if db.execute(select(quality.c.id).where(quality.c.id==key)).first():db.execute(update(quality).where(quality.c.id==key).values(**values))
    elif conflicts:db.execute(quality.insert().values(id=key,created_at=now(),**values))
    event(db,p,'certificate_compared',ident,row['company_id'],{'conflicts':conflicts,'document_id':doc.id});db.commit()
    return {'conflicts':conflicts,'existing_certificate_overwritten':False,'public_metadata':parsed,'authority_validated':False}

from .fiscal_calendar import register as register_calendar
register_calendar(router)

from .lote4_lifecycle import register as register_lifecycle
register_lifecycle(router)
