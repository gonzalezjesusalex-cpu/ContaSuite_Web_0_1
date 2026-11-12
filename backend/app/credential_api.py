from datetime import datetime,timezone,date
from zoneinfo import ZoneInfo
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Response,Query
from pydantic import BaseModel,ConfigDict,Field,SecretStr
from sqlalchemy import select,update,inspect
from sqlalchemy.exc import IntegrityError
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from .database import session
from .models import Company,Document,DocumentCompanyLink,now
from .security import auth,Principal,utc
from .credential_models import metadata,services,grants,credentials,versions,certificates,audit,settings
from .credential_crypto import VaultCipher,VaultLocked

PERMISSIONS={'metadata','create','modify','reveal','certificates','history','alerts','permissions'}
router=APIRouter(prefix='/api/credentials',tags=['Credenciales y certificados'])
def ready(db):
    if not all(inspect(db.connection()).has_table(t.name) for t in metadata.sorted_tables):raise HTTPException(503,'Módulo pendiente de migración autorizada.')
def no_cache(response):
    response.headers['Cache-Control']='no-store, private';response.headers['Pragma']='no-cache'
def allowed(p,db,cid,permission):
    p.require_company(cid)
    if not db.get(Company,cid):raise HTTPException(404,'Empresa no encontrada.')
    # Existing admins can manage metadata, but reveal always needs an explicit grant.
    if p.admin and permission!='reveal':return
    if not db.execute(select(grants.c.user_id).where(grants.c.user_id==p.subject,grants.c.company_id==cid,grants.c.permission==permission)).first():raise HTTPException(403,'Sin permiso para esta operación.')
def event(db,p,cid,action,ident=None,details=None):
    db.execute(audit.insert().values(id=str(uuid4()),company_id=cid,actor_id=p.subject,action=action,record_id=ident,created_at=now(),metadata=details or {}))
def public_credential(row):
    return {k:row[k] for k in ['id','company_id','service_id','label','revision','archived','created_at','updated_at']}

def temporal(row,thresholds=(60,30,15),stamp=None):
    stamp=stamp or now();end=row.get('valid_until');start=row.get('valid_from')
    if not start or not end:return {'state':'unknown','days_remaining':None,'threshold':None}
    start,end=utc(start),utc(end)
    days=(end.astimezone(ZoneInfo('America/Mexico_City')).date()-stamp.astimezone(ZoneInfo('America/Mexico_City')).date()).days
    state='pending_verification' if stamp<start else 'expired' if stamp>end else 'expiring' if days<=max(thresholds) else 'valid'
    return {'state':state,'days_remaining':days,'threshold':next((t for t in sorted(thresholds) if days<=t),None) if days>=0 else None}

def parse_public_certificate(payload):
    try:
        if len(payload)>1024*1024:raise ValueError()
        cert=x509.load_pem_x509_certificate(payload) if payload.lstrip().startswith(b'-----BEGIN CERTIFICATE-----') else x509.load_der_x509_certificate(payload)
        return dict(serial=format(cert.serial_number,'X'),subject=cert.subject.rfc4514_string()[:1000],fingerprint=cert.fingerprint(hashes.SHA256()).hex(),valid_from=cert.not_valid_before_utc,valid_until=cert.not_valid_after_utc)
    except Exception:raise HTTPException(422,'No es un certificado público X.509 admitido.') from None

@router.get('/companies/{cid}')
def overview(cid:str,response:Response,p:Principal=Depends(auth),db=Depends(session)):
    no_cache(response);ready(db);allowed(p,db,cid,'metadata')
    items=[public_credential(r) for r in db.execute(select(credentials).where(credentials.c.company_id==cid)).mappings()]
    thresholds=db.execute(select(settings.c.thresholds).where(settings.c.id==1)).scalar() or [60,30,15]
    certs=[{**dict(r),**temporal(r,thresholds),'authority_validated':False} for r in db.execute(select(certificates).where(certificates.c.company_id==cid)).mappings()]
    event(db,p,cid,'metadata_read');db.commit()
    perms=[a for a in PERMISSIONS if (p.admin and a!='reveal') or db.execute(select(grants.c.permission).where(grants.c.user_id==p.subject,grants.c.company_id==cid,grants.c.permission==a)).first()]
    return dict(credentials=items,certificates=certs,services=[dict(r) for r in db.execute(select(services)).mappings()],permissions=perms,reveal_enabled=False,thresholds=thresholds)

class CredentialIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    service_id:str=Field(max_length=50)
    # Label is deliberately not free-form: avoids accidental passwords in audit or overview.
    label:str=Field('Acceso',min_length=1,max_length=100)
    secret:SecretStr=Field(min_length=1,max_length=4096)
    revision:int=Field(0,ge=0)

@router.post('/companies/{cid}/secrets')
def store(cid:str,payload:CredentialIn,response:Response,ident:str|None=None,p:Principal=Depends(auth),db=Depends(session)):
    no_cache(response);ready(db);allowed(p,db,cid,'modify' if ident else 'create')
    if p.bootstrap or not p.session_id:raise HTTPException(403,'Se requiere una sesión personal.')
    if not db.execute(select(services.c.id).where(services.c.id==payload.service_id)).first():raise HTTPException(422,'Servicio no registrado.')
    old=db.execute(select(credentials).where(credentials.c.id==ident,credentials.c.company_id==cid)).mappings().first() if ident else None
    if ident and not old:raise HTTPException(404,'Credencial no encontrada.')
    if (old['revision'] if old else 0)!=payload.revision:raise HTTPException(409,'El registro cambió; actualiza.')
    ident=ident or str(uuid4())
    try:envelope=VaultCipher.from_environment().seal(payload.secret.get_secret_value(),cid,ident)
    except VaultLocked:raise HTTPException(423,'Bóveda bloqueada: falta configurar el proveedor de claves.') from None
    revision=payload.revision+1
    try:
        if old:
            if not db.execute(update(credentials).where(credentials.c.id==ident,credentials.c.revision==payload.revision).values(envelope=envelope,revision=revision,updated_at=now())).rowcount:raise HTTPException(409,'Edición concurrente.')
        else:db.execute(credentials.insert().values(id=ident,company_id=cid,service_id=payload.service_id,label='Acceso',envelope=envelope,revision=revision,archived=False,created_at=now(),updated_at=now()))
        db.execute(versions.insert().values(credential_id=ident,revision=revision,envelope=envelope,actor_id=p.subject,created_at=now()))
        event(db,p,cid,'credential_modified' if old else 'credential_created',ident,{'revision':revision});db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,'Edición concurrente.') from None
    return {'id':ident,'revision':revision}

@router.post('/companies/{cid}/secrets/{ident}/reveal')
def reveal(cid:str,ident:str,response:Response,p:Principal=Depends(auth),db=Depends(session)):
    no_cache(response);ready(db);allowed(p,db,cid,'reveal')
    if not db.execute(select(credentials.c.id).where(credentials.c.id==ident,credentials.c.company_id==cid)).first():raise HTTPException(404,'Credencial no encontrada.')
    event(db,p,cid,'reveal_blocked',ident);db.commit()
    raise HTTPException(423,'Revelación deshabilitada hasta integrar reautenticación reciente y proveedor de claves.',headers={'Cache-Control':'no-store'})

@router.delete('/companies/{cid}/secrets/{ident}')
def archive(cid:str,ident:str,response:Response,revision:int=Query(ge=1),p:Principal=Depends(auth),db=Depends(session)):
    no_cache(response);ready(db);allowed(p,db,cid,'modify')
    changed=db.execute(update(credentials).where(credentials.c.id==ident,credentials.c.company_id==cid,credentials.c.revision==revision).values(archived=True,revision=revision+1,updated_at=now()))
    if not changed.rowcount:raise HTTPException(409,'El registro cambió o no está disponible.')
    event(db,p,cid,'credential_archived',ident);db.commit();return {'archived':True}

class CertificateIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['fiel','csd','unknown']='unknown'
    document_id:str|None=Field(None,max_length=36)
    notes:str=Field('',max_length=2000)

@router.post('/companies/{cid}/certificates')
def add_certificate(cid:str,payload:CertificateIn,response:Response,p:Principal=Depends(auth),db=Depends(session)):
    no_cache(response);ready(db);allowed(p,db,cid,'certificates')
    company=db.get(Company,cid);parsed={};origin='manual'
    if payload.document_id:
        doc=db.get(Document,payload.document_id)
        linked=doc and (doc.company_id==cid or db.execute(select(DocumentCompanyLink.document_id).where(DocumentCompanyLink.document_id==doc.id,DocumentCompanyLink.company_id==cid)).first())
        if not linked or not doc.name.lower().endswith('.cer'):raise HTTPException(422,'Selecciona un CER público vinculado a esta empresa. No se procesan KEY.')
        from .storage.router import storage_service
        from .storage.providers import StorageError
        try:
            with storage_service().read(p.storage_actor(),doc.id) as content:parsed=parse_public_certificate(content.stream.read(1024*1024+1))
        except StorageError:raise HTTPException(409,'No se pudo leer el certificado público.') from None
        origin='cs_storage'
        from .storage.classifier import RFC,valid_rfc
        rfcs={r for r in RFC.findall(parsed['subject'].upper()) if valid_rfc(r)}
        if rfcs and company.rfc not in rfcs:raise HTTPException(422,'El RFC del certificado no coincide con la empresa.')
    ident=str(uuid4())
    try:
        db.execute(certificates.insert().values(id=ident,company_id=cid,rfc=company.rfc,kind=payload.kind,document_id=payload.document_id,origin=origin,reviewed_at=now(),notes=payload.notes,revision=1,**parsed))
        event(db,p,cid,'certificate_created',ident,{'kind':payload.kind,'origin':origin});db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,'Certificado ya registrado.') from None
    return {'id':ident,'authority_validated':False}

@router.get('/companies/{cid}/history')
def history(cid:str,response:Response,p:Principal=Depends(auth),db=Depends(session)):
    no_cache(response);ready(db);allowed(p,db,cid,'history')
    rows=[dict(r) for r in db.execute(select(audit).where(audit.c.company_id==cid).order_by(audit.c.created_at.desc()).limit(100)).mappings()]
    event(db,p,cid,'history_read');db.commit();return rows

class CertificateEdit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    kind:Literal['fiel','csd','unknown']
    notes:str=Field('',max_length=2000)

@router.put('/companies/{cid}/certificates/{ident}')
def edit_certificate(cid:str,ident:str,payload:CertificateEdit,response:Response,p:Principal=Depends(auth),db=Depends(session)):
    no_cache(response);ready(db);allowed(p,db,cid,'certificates')
    old=db.execute(select(certificates).where(certificates.c.id==ident,certificates.c.company_id==cid)).mappings().first()
    if not old:raise HTTPException(404,'Certificado no encontrado.')
    try:
        result=db.execute(update(certificates).where(certificates.c.id==ident,certificates.c.revision==payload.revision).values(kind=payload.kind,notes=payload.notes,reviewed_at=now(),revision=payload.revision+1))
        if not result.rowcount:raise HTTPException(409,'El certificado cambió; actualiza.')
        event(db,p,cid,'certificate_modified',ident,{'before_kind':old['kind'],'after_kind':payload.kind,'revision':payload.revision+1});db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,'Certificado ya registrado con ese tipo.') from None
    return {'revision':payload.revision+1}

class ServiceIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    label:str=Field(min_length=1,max_length=100)
@router.post('/services')
def service(payload:ServiceIn,response:Response,p:Principal=Depends(auth),db=Depends(session)):
    no_cache(response);ready(db);p.require_admin()
    if not payload.label.strip():raise HTTPException(422,'Nombre requerido.')
    ident=str(uuid4());db.execute(services.insert().values(id=ident,label=payload.label.strip()))
    event(db,p,None,'service_created',ident);db.commit();return {'id':ident}

class GrantIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    user_id:str=Field(max_length=36)
    permission:Literal['metadata','create','modify','reveal','certificates','history','alerts','permissions']
    enabled:bool
@router.put('/companies/{cid}/permissions')
def grant(cid:str,payload:GrantIn,response:Response,p:Principal=Depends(auth),db=Depends(session)):
    no_cache(response);ready(db);p.require_admin();allowed(p,db,cid,'permissions')
    from .models import UserAccount,UserCompanyGrant
    user=db.get(UserAccount,payload.user_id)
    if not user or not user.enabled or (not user.admin and not db.get(UserCompanyGrant,(user.id,cid))):raise HTTPException(422,'Usuario sin acceso a la empresa.')
    condition=(grants.c.company_id==cid)&(grants.c.user_id==user.id)&(grants.c.permission==payload.permission)
    db.execute(grants.delete().where(condition))
    if payload.enabled:db.execute(grants.insert().values(company_id=cid,user_id=user.id,permission=payload.permission))
    event(db,p,cid,'permission_changed',details=payload.model_dump());db.commit();return {'saved':True}
