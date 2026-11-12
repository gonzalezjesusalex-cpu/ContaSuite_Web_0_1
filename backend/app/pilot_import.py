"""Pilot-only local import using existing reconciliation staging and CS-Storage contracts."""
import hashlib
import json
import os
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update, text
from sqlalchemy.exc import IntegrityError
from .database import session
from .models import Company, Document, DocumentVersion, DocumentCompanyLink, DocumentClassificationReview as Review, StorageSource, now
from .security import auth, Principal, utc
from .company_import_models import sessions, rows
from .company_import_api import ready, audit
from .company_lifecycle import normalize_rfc, archive_metadata
from .storage.classifier import valid_rfc
from .storage.local import LocalFolderProvider
from .storage.service import StorageService
from .storage.router import storage_service, storage_http_error
from .storage.providers import StorageError
from .pilot_scan import scan, roots_from_environment, configured_limits, SECRET_PATTERNS
from .document_identity import lock, blocked, identities

router = APIRouter(prefix='/api/pilot-imports', tags=['Piloto local'])
SCAN_SLOT = threading.BoundedSemaphore(1)


def authorized(p, db):
    p.require_admin()
    if p.bootstrap or not p.session_id: raise HTTPException(403, 'Se requiere una sesión personal.')
    expected = os.getenv('CS_PILOT_DATABASE', '')
    url = db.get_bind().url
    if (os.getenv('CS_PILOT_ENABLED') != '1' or not expected.startswith('contasuite_pilot_') or
        url.get_backend_name() != 'postgresql' or url.database != expected or url.host not in {'127.0.0.1','localhost'}):
        raise HTTPException(423, 'Piloto deshabilitado: requiere PostgreSQL local exclusivo y configuración explícita.')
    ready(db)


def paths():
    result = roots_from_environment()
    if len(result) != 2: raise StorageError('unauthorized_root')
    return [LocalFolderProvider(path,tuple(result)).root for path in result]


def preview_scan(selected, exclusions):
    if not SCAN_SLOT.acquire(blocking=False): raise HTTPException(409, 'Hay otro análisis local en curso.')
    try: return scan(selected, exclusions=exclusions,**configured_limits())
    finally: SCAN_SLOT.release()


def item(db, p, ident, *, locked=False):
    authorized(p, db)
    query = select(sessions).where(sessions.c.id==ident, sessions.c.source=='local_pilot', sessions.c.owner_id==p.subject)
    if locked: query = query.with_for_update()
    value = db.execute(query).mappings().first()
    if not value: raise HTTPException(404, 'Vista previa no disponible.')
    if value['status'] != 'committed' and utc(value['expires_at']) <= now(): raise HTTPException(410, 'Vista previa caducada; vuelve a analizar.')
    return value


@router.get('/options')
def options(p:Principal=Depends(auth), db=Depends(session)):
    authorized(p, db)
    try:
        return {'folders':[{'id':str(i),'name':path.name,'path':str(path)} for i,path in enumerate(roots_from_environment())],
                'limits':configured_limits(), 'excluded':list(SECRET_PATTERNS)}
    except StorageError as e: raise storage_http_error(e) from None


class PreviewIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    folders:list[Literal['0','1']]=Field(min_length=2,max_length=2)
    authorized_read:bool
    exclusions:list[str]=Field(default_factory=list,max_length=30)


@router.get('')
def recent(p:Principal=Depends(auth),db=Depends(session)):
    authorized(p,db)
    return {'items':[{'id':v.id,'status':v.status,'created_at':v.created_at} for v in db.execute(
        select(sessions.c.id,sessions.c.status,sessions.c.created_at).where(sessions.c.source=='local_pilot',
            sessions.c.owner_id==p.subject).order_by(sessions.c.created_at.desc()).limit(10))]}


@router.post('/preview')
def preview(payload:PreviewIn, p:Principal=Depends(auth), db=Depends(session)):
    authorized(p, db)
    if not payload.authorized_read or set(payload.folders)!={'0','1'}: raise HTTPException(422, 'Autoriza la lectura y selecciona las dos carpetas.')
    if any(len(s)>120 for s in payload.exclusions): raise HTTPException(422, 'Exclusión fuera de límites.')
    try: result = preview_scan(paths(), payload.exclusions)
    except StorageError as e: raise storage_http_error(e) from None
    ident = str(uuid4())
    # Include current catalogue conflicts, without merging identities or exposing other users' data.
    existing=list(db.execute(select(identities.c.uuid,identities.c.content_hash).join(DocumentVersion,
        DocumentVersion.id==identities.c.version_id).join(Document,Document.id==DocumentVersion.document_id)
        .where(DocumentVersion.number==Document.storage_revision)))
    hashes=set(db.scalars(select(DocumentVersion.sha256).join(Document,Document.id==DocumentVersion.document_id)
        .where(DocumentVersion.number==Document.storage_revision)))
    for doc in result['documents']:
        uuid=doc['result']['evidence'].get('cfdi_uuid')
        doc['conflict']=doc['conflict'] or bool(uuid and any(u==uuid and h!=doc['sha256'] for u,h in existing))
        doc['duplicate']=doc['duplicate'] or doc['sha256'] in hashes
    company_rows=[]
    for folder in result['folders']:
        candidates={}
        for doc in result['documents']:
            if doc['folder']!=folder['id']:continue
            for c in doc['result'].get('identities',[]):
                candidates[c['rfc']] = c
            for c in doc['result']['evidence'].get('rfcs',[]):
                candidates.setdefault(c['rfc'], {'rfc':c['rfc'],'name':'','source':'Contenido documental; nombre pendiente'})
        company_rows.append({'kind':'company','folder':folder['id'],'rfc':'','name':'','candidates':list(candidates.values())})
    # Never pick a counterparty or folder-derived identity automatically.
    summary={'folders':result['folders'],'exclusions':payload.exclusions,'revision':0,'fingerprint':result['fingerprint'],
             'documents':len(result['documents']),'conflicts':sum(d['conflict'] for d in result['documents'])}
    db.execute(sessions.insert().values(id=ident,owner_id=p.subject,idempotency_key=hashlib.sha256(ident.encode()).hexdigest(),
        source='local_pilot',source_sha256=result['fingerprint'],summary=summary,created_at=now(),expires_at=now()+timedelta(hours=4),status='preview'))
    for number,proposal in enumerate(company_rows+[{**d,'kind':'document'} for d in result['documents']],1):
        db.execute(rows.insert().values(session_id=ident,number=number,proposal=proposal,revision=0))
    audit(db,p,ident,'pilot_preview',{'documents':len(result['documents'])});db.commit()
    return load(ident,p,db)


@router.get('/{ident}')
def load(ident:str,p:Principal=Depends(auth),db=Depends(session)):
    value=item(db,p,ident)
    proposals=[{'number':r.number,'revision':r.revision,**r.proposal} for r in db.execute(select(rows).where(rows.c.session_id==ident).order_by(rows.c.number))]
    return {'id':ident,'status':value['status'],'summary':value['summary'],'rows':proposals}


class LinkIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    folder:Literal['0','1']
    role:Literal['owner','issuer','receiver']


class DecisionIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=0)
    rfc:str=Field('',max_length=30)
    name:str=Field('',max_length=220)
    document_type:Literal['unknown','cfdi','declaration','acknowledgement','certificate','other']='unknown'
    include:bool=True
    links:list[LinkIn]=Field(default_factory=list,max_length=6)
    reason:str=Field(min_length=3,max_length=500)


@router.put('/{ident}/rows/{number}')
def decide(ident:str,number:int,payload:DecisionIn,p:Principal=Depends(auth),db=Depends(session)):
    value=item(db,p,ident,locked=True)
    if value['status']!='preview':raise HTTPException(409,'Importación ya confirmada.')
    row=db.execute(select(rows).where(rows.c.session_id==ident,rows.c.number==number)).mappings().first()
    if not row or row['revision']!=payload.revision:raise HTTPException(409,'La propuesta cambió; actualiza.')
    proposal=dict(row['proposal'])
    if proposal['kind']=='company':
        rfc=normalize_rfc(payload.rfc)
        if not valid_rfc(rfc) or not payload.name.strip():raise HTTPException(422,'RFC válido y razón social revisada requeridos.')
        proposal.update(rfc=rfc,name=payload.name.strip())
    else:
        proposal.update(type=payload.document_type,include=payload.include,links=[l.model_dump() for l in payload.links])
    proposal['decision']={'actor':p.subject,'at':now().isoformat(),'reason':payload.reason.strip()}
    db.execute(update(rows).where(rows.c.session_id==ident,rows.c.number==number).values(proposal=proposal,revision=payload.revision+1))
    summary={**value['summary'],'revision':value['summary']['revision']+1}
    db.execute(update(sessions).where(sessions.c.id==ident).values(summary=summary))
    # Keep every revision in existing aggregate/decision audit. No file contents in logs.
    audit(db,p,ident,'pilot_decision',{'row':number,'revision':payload.revision+1,'before':row['proposal'],'after':proposal})
    db.commit();return load(ident,p,db)


class ConfirmIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=0)
    confirmed:bool


class BorrowedSessions:
    """Use core services in the caller's one transaction; never commit/close independently."""
    def __init__(self,db):self.db=db
    @contextmanager
    def begin(self):
        yield self.db
        self.db.flush()
    @contextmanager
    def __call__(self):yield self.db


@router.post('/{ident}/confirm')
def confirm(ident:str,payload:ConfirmIn,p:Principal=Depends(auth),db=Depends(session),service:StorageService=Depends(storage_service)):
    authorized(p,db)
    if not payload.confirmed:raise HTTPException(422,'Confirmación explícita requerida dentro de ContaSuite.')
    # Lock order matches all document writers; session lock serializes edits/confirmations.
    lock(db)
    value=item(db,p,ident,locked=True)
    if value['status']=='committed':return {'idempotent':True,**value['summary']['imported']}
    if value['summary']['revision']!=payload.revision:raise HTTPException(409,'Revisa la versión actual antes de confirmar.')
    try:selected=paths()
    except StorageError as e:
        db.rollback();raise storage_http_error(e) from None
    if [str(p) for p in selected]!=[f['path'] for f in value['summary']['folders']]:raise HTTPException(409,'La autorización de carpetas cambió.')
    records=[r.proposal for r in db.execute(select(rows).where(rows.c.session_id==ident).order_by(rows.c.number))]
    companies=[r for r in records if r['kind']=='company'];docs=[r for r in records if r['kind']=='document']
    if len({c['rfc'] for c in companies})!=2 or any(not valid_rfc(c['rfc']) or not c['name'] or not c.get('decision') for c in companies):
        raise HTTPException(422,'Revisa expresamente las dos identidades empresariales distintas.')
    try:
        current=preview_scan(selected,value['summary']['exclusions'])
        if current['fingerprint']!=value['source_sha256']:raise HTTPException(409,'Los archivos cambiaron: vuelve a analizar sin importar esta propuesta.')
        core=StorageService(BorrowedSessions(db),replace(service.settings,allowed_roots=tuple(selected)))
        actor=p.storage_actor();mapping={}
        for c in sorted(companies,key=lambda c:c['rfc']):
            # Same normalized identity mutex as the existing company writers.
            db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'),{'key':c['rfc']}) if db.bind.dialect.name=='postgresql' else None
            matches=[x for x in db.scalars(select(Company)) if normalize_rfc(x.rfc)==c['rfc']]
            if len(matches)>1:raise HTTPException(409,'Identidad empresarial duplicada en catálogo; requiere conciliación.')
            if matches:
                company=matches[0]
                _,archives=archive_metadata(db,[company.id])
                if archives.get(company.id,{}).get('archived'):raise HTTPException(409,'Empresa archivada: no se reactiva ni modifica desde el piloto.')
            else:
                company=Company(name=c['name'],rfc=c['rfc'],person_type='Moral' if len(c['rfc'])==12 else 'Física',
                                regime='Por revisar',notes='Alta piloto local; metadatos fiscales pendientes de revisión.')
                db.add(company);db.flush()
            mapping[c['folder']]=company.id
        sources={}
        for i,path in enumerate(selected):
            candidates=list(db.scalars(select(StorageSource).where(StorageSource.kind=='local_folder',StorageSource.root_path==str(path))))
            if len(candidates)>1:raise HTTPException(409,'Origen local duplicado; revisa configuración.')
            if candidates:
                source=candidates[0]
                if not source.enabled or source.configuration.get('pilot_import') is not True:raise HTTPException(409,'La carpeta pertenece a otro origen; no se modifica automáticamente.')
            else:
                core._local(path,SECRET_PATTERNS+tuple(value['summary']['exclusions']))
                source=StorageSource(id=str(uuid4()),kind='local_folder',label='Piloto '+str(i+1),root_path=str(path),
                       interval_minutes=0,configuration={'pilot_import':True,'exclusions':list(SECRET_PATTERNS)+value['summary']['exclusions']})
                db.add(source);db.flush();core._event(db,actor,'source_registered',source_id=source.id)
            sources[str(i)]=source.id
        imported=[]
        for row in docs:
            if not row['include'] or row['error']:continue
            observed=core.observe_external(actor,sources[row['folder']],row['key'])
            version=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==observed.id,DocumentVersion.number==observed.revision))
            if version.sha256!=row['sha256']:raise HTTPException(409,'El contenido cambió durante la importación; no se guardaron cambios.')
            chosen=[{'company_id':mapping[l['folder']],'role':l['role']} for l in row['links']]
            result={**row['result'],'type':row['type'],'links':chosen,'automatic':False}
            doc=db.get(Document,observed.id)
            latest=db.scalar(select(Review).where(Review.version_id==version.id).order_by(Review.created_at.desc(),Review.id).limit(1))
            existing={(l.company_id,l.role) for l in db.scalars(select(DocumentCompanyLink).where(DocumentCompanyLink.document_id==doc.id))}
            if doc.company_id:existing.add((doc.company_id,'owner'))
            desired={(l['company_id'],l['role']) for l in chosen}
            apply=latest is None or bool(row.get('decision'))
            if latest and latest.status=='resolved' and desired==existing and row['type']==doc.document_type:apply=False
            proposed={(l['company_id'],l['role']) for l in latest.proposed_links} if latest else set()
            if apply and latest and (latest.status!='pending' or proposed!=desired or row['type']!=doc.document_type):
                # Reimport corrections append a new review; never overwrite human or pending snapshots.
                if latest.status=='pending':latest.status='superseded'
                evidence={k:v for k,v in latest.evidence.items() if k!='human_decision'}
                db.add(Review(document_id=doc.id,version_id=version.id,evidence={**evidence,
                    'pilot_previous_review':latest.id,'pilot_session':ident,'pilot_reason':row['decision']['reason']}))
                db.flush()
            if apply:
                if row.get('decision'):doc.document_type=row['type']
                core.apply_classification(actor,observed.id,observed.revision,result)
            imported.append((observed.id,observed.revision,chosen,row))
        # Resolve only after all UUID participants have been registered.
        for ident_doc,revision,chosen,row in imported:
            version=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==ident_doc,DocumentVersion.number==revision))
            pending=db.scalar(select(Review).where(Review.version_id==version.id,Review.status=='pending'))
            if pending and chosen and not blocked(db,version.id) and row.get('decision'):
                core.resolve_review(actor,ident_doc,pending.id,revision,'correct',chosen,reason=row['decision']['reason'])
        result={'companies':sorted(mapping.values()),'documents':len(imported),'pending':sum(db.get(Document,d[0]).classification_status=='pending' for d in imported)}
        db.execute(update(sessions).where(sessions.c.id==ident).values(status='committed',summary={**value['summary'],'imported':result}))
        audit(db,p,ident,'pilot_confirmed',{'companies':2,'documents':len(imported),'pending':result['pending']})
        db.commit();return {'idempotent':False,**result}
    except StorageError as e:
        db.rollback();raise storage_http_error(e) from None
    except HTTPException:
        db.rollback();raise
    except IntegrityError:
        db.rollback();raise HTTPException(409,'El catálogo cambió simultáneamente; revisa y repite sin duplicar registros.') from None
