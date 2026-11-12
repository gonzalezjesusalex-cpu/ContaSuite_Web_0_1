"""Append-only decisions, with legacy verification table retained as current projection."""
import hashlib
from uuid import uuid4
from sqlalchemy import MetaData,Table,Column,String,Integer,DateTime,ForeignKey,select,inspect,update
from fastapi import HTTPException
from .models import Company,Document,DocumentVersion,now
from .fiscal_control import records
from .integral_models import verification
metadata=MetaData()
decisions=Table('fiscal_verification_decisions',metadata,
    Column('id',String(64),primary_key=True),Column('record_id',ForeignKey(records.c.id),nullable=False),
    Column('record_revision',Integer,nullable=False),Column('company_id',ForeignKey(Company.id),nullable=False),
    Column('period_id',String(12),nullable=False),Column('document_id',ForeignKey(Document.id),nullable=False),
    Column('version_id',ForeignKey(DocumentVersion.id),nullable=False),Column('actor_id',String(100),nullable=False),
    Column('verified_at',DateTime(timezone=True),nullable=False),Column('origin',String(20),nullable=False))
def ready(db):
    if not inspect(db.connection()).has_table(decisions.name):raise HTTPException(503,'Historial de verificación pendiente de actualización explícita del esquema.')

def review_condition(db,row):
    """No provider access. A changed revision/version suspends the current decision."""
    from .models import DocumentCompanyLink
    current=db.execute(select(verification).where(verification.c.record_id==row['id'])).mappings().first()
    doc=db.get(Document,current['document_id']) if current else None
    version=db.get(DocumentVersion,current['version_id']) if current else None
    represented=current and db.scalar(select(decisions.c.id).where(
        decisions.c.record_id==row['id'],decisions.c.record_revision==current['record_revision'],
        decisions.c.version_id==current['version_id'],decisions.c.actor_id==current['actor_id']))
    owners=set(db.scalars(select(DocumentCompanyLink.company_id).where(DocumentCompanyLink.document_id==doc.id))) if doc else set()
    if doc and doc.company_id:owners.add(doc.company_id)
    from .document_identity import blocked,verification_allowed
    valid=bool(represented and verification_allowed(db,current['version_id'],current['verified_at']) and current['record_revision']==row['revision'] and current['company_id']==row['company_id'] and
        doc and version and version.document_id==doc.id and version.number==doc.storage_revision and version.sha256 and row['company_id'] in owners)
    return valid,dict(fiscal_revision=row['revision'],decision=represented or None,
        document_revision=doc.storage_revision if doc else None,version_id=version.id if version else None,identity_conflict=blocked(db,version.id) if version else False)
def capture_legacy(db,record_id=None):
    # Called only by explicit migration. Never invent earlier decisions that no longer exist.
    for r in db.execute(select(verification).where(verification.c.record_id==record_id) if record_id else select(verification)).mappings():
        record=db.execute(select(records).where(records.c.id==r['record_id'])).mappings().first()
        if not record:raise RuntimeError('Orphan verification; reconcile on a copy first')
        key=hashlib.sha256(('legacy:'+r['record_id']+':'+str(r['record_revision'])+':'+r['version_id']+':'+r['actor_id']).encode()).hexdigest()
        represented=db.scalar(select(decisions.c.id).where(decisions.c.record_id==r['record_id'],decisions.c.record_revision==r['record_revision'],decisions.c.version_id==r['version_id'],decisions.c.actor_id==r['actor_id']))
        if not represented:
            db.execute(decisions.insert().values(id=key,period_id=record['period_id'],origin='legacy_snapshot',**dict(r)))
def record_verification(db,p,ident,revision,document_id):
    ready(db);p.require_admin()
    from .document_identity import lock
    lock(db)
    row=db.execute(select(records).where(records.c.id==ident).with_for_update()).mappings().first()
    if not row or row['status']!='fulfilled' or row['revision']!=revision:raise HTTPException(409,'La revisión fiscal cambió.')
    p.require_company(row['company_id'],write=True)
    from .integral_api import document,version,linked
    doc=document(db,p,document_id);v=version(db,doc)
    from .document_identity import blocked,available,identities
    if available(db) and doc.name.lower().endswith('.xml') and not db.scalar(select(identities.c.version_id).where(identities.c.version_id==v.id)):
        raise HTTPException(409,'Analiza la identidad XML de esta versión antes de verificarla.')
    if blocked(db,v.id):raise HTTPException(409,'Identidad documental en conflicto; requiere revisión antes de verificar.')
    if row['company_id'] not in linked(db,doc):raise HTTPException(422,'Evidencia de otra empresa.')
    from .storage.router import storage_service
    from .storage.providers import StorageError
    try:
        with storage_service().read(p.storage_actor(),document_id) as content:
            digest=hashlib.sha256()
            while chunk:=content.stream.read(65536):digest.update(chunk)
        if not v.sha256 or digest.hexdigest()!=v.sha256:raise HTTPException(409,'Contenido no comprobable para la versión seleccionada.')
    except StorageError:raise HTTPException(409,'Contenido no disponible; se conserva la verificación anterior.') from None
    if not db.execute(update(Document).where(Document.id==doc.id,Document.storage_revision==v.number).values(storage_revision=v.number)).rowcount:raise HTTPException(409,'Versión documental concurrente.')
    if not db.execute(update(records).where(records.c.id==ident,records.c.revision==revision).values(revision=revision)).rowcount:raise HTTPException(409,'Revisión fiscal concurrente.')
    values=dict(record_id=ident,record_revision=revision,company_id=row['company_id'],document_id=doc.id,version_id=v.id,actor_id=p.subject,verified_at=now())
    current=db.execute(select(verification).where(verification.c.record_id==ident)).mappings().first()
    from .document_identity import verification_allowed
    same=current and verification_allowed(db,v.id,current['verified_at']) and all(current[k]==values[k] for k in ('record_revision','document_id','version_id','actor_id','company_id'))
    existing=db.execute(select(decisions).where(decisions.c.record_id==ident,decisions.c.record_revision==revision,decisions.c.version_id==v.id,decisions.c.actor_id==p.subject,decisions.c.verified_at==current['verified_at'])).mappings().first() if same else None
    key=existing['id'] if existing else hashlib.sha256(str(uuid4()).encode()).hexdigest()
    if existing:values['verified_at']=existing['verified_at']
    else:
        # Defend legacy current rows inserted by old integrations after schema update.
        capture_legacy(db,ident)
        db.execute(decisions.insert().values(id=key,period_id=row['period_id'],origin='human_content_check',**values))
    old=db.scalar(select(verification.c.record_id).where(verification.c.record_id==ident))
    if old:db.execute(update(verification).where(verification.c.record_id==ident).values(**values))
    else:db.execute(verification.insert().values(**values))
    return {'decision_id':key,'verified_by_office':True,'sat_validated':False,'status_changed':False,'idempotent':bool(existing)}
