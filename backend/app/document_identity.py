"""Version-bound CFDI identity; conflicts feed the existing classification review queue."""
import hashlib,json
from sqlalchemy import MetaData,Table,Column,String,Boolean,DateTime,ForeignKey,select,update,inspect,text
from .models import Document,DocumentVersion,DocumentCompanyLink,DocumentClassificationReview as Review,StorageEvent,now
metadata=MetaData()
identities=Table('document_cfdi_identities',metadata,
    Column('version_id',ForeignKey(DocumentVersion.id),primary_key=True),
    Column('uuid',String(36),index=True),Column('content_hash',String(64),nullable=False),
    Column('requires_review',Boolean,nullable=False),Column('condition_hash',String(64),nullable=False),
    Column('reviewed_by',String(100)),Column('reviewed_at',DateTime(timezone=True)),Column('review_id',ForeignKey(Review.id)))

def available(db):return inspect(db.connection()).has_table(identities.name)
def lock(db):
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(440042)'))
def blocked(db,version_id):
    return bool(db.scalar(select(identities.c.requires_review).where(identities.c.version_id==version_id))) if available(db) else False
def verification_allowed(db,version_id,verified_at):
    if not available(db):return True
    r=db.execute(select(identities).where(identities.c.version_id==version_id)).mappings().first()
    if not r:
        version=db.get(DocumentVersion,version_id)
        return not version or not version.original_name.lower().endswith('.xml')
    from .security import utc
    return not r['requires_review'] and (not r['reviewed_at'] or utc(verified_at)>=utc(r['reviewed_at']))

def register(db,doc,version,result,actor='identity-parser'):
    """Caller holds identity lock and document CAS. Never merges or opens providers."""
    if not available(db):return
    uuid=result['evidence'].get('cfdi_uuid');invalid=result['evidence'].get('uuid_status')=='contradictory'
    previous=list(db.execute(select(identities).join(DocumentVersion,DocumentVersion.id==identities.c.version_id)
        .where(DocumentVersion.document_id==doc.id,DocumentVersion.number<version.number)).mappings())
    replaced=any(r['uuid'] and r['uuid']!=uuid for r in previous)
    existing=db.execute(select(identities).where(identities.c.version_id==version.id)).mappings().first()
    if not existing:
        db.execute(identities.insert().values(version_id=version.id,uuid=uuid,content_hash=version.sha256 or '',requires_review=False,condition_hash=''))
    elif existing['uuid']!=uuid or existing['content_hash']!=(version.sha256 or ''):
        # Parser results cannot silently rewrite an identity already recorded for these bytes.
        invalid=True
    peers=list(db.execute(select(identities).join(DocumentVersion,DocumentVersion.id==identities.c.version_id)
        .join(Document,Document.id==DocumentVersion.document_id).where(identities.c.uuid==uuid,
            DocumentVersion.number==Document.storage_revision)).mappings()) if uuid else []
    conflict=len({r['content_hash'] for r in peers})>1
    if not (conflict or invalid or replaced):return
    reason='uuid_content_conflict' if conflict else 'document_identity_changed' if replaced else 'uuid_ambiguous'
    affected=peers if conflict else [dict(version_id=version.id)]
    condition=hashlib.sha256(json.dumps({'versions':sorted((r['version_id'],r.get('content_hash','')) for r in affected),
        'previous':[] if conflict else sorted(r['version_id'] for r in previous),'reason':reason},sort_keys=True).encode()).hexdigest()
    for item in affected:
        current=db.execute(select(identities).where(identities.c.version_id==item['version_id'])).mappings().one()
        if current['condition_hash']==condition:
            if item['version_id']==version.id and current['requires_review']:
                result['evidence']={**result['evidence'],'reason':reason,'identity':{'uuid':current['uuid'],'requires_review':True,'condition_hash':condition,'conflicting_versions':sorted(r['version_id'] for r in affected),'authority_validated':False}}
                result['automatic']=False
            continue
        db.execute(update(identities).where(identities.c.version_id==item['version_id']).values(
            requires_review=True,condition_hash=condition,reviewed_by=None,reviewed_at=None,review_id=None))
        v=db.get(DocumentVersion,item['version_id']);peer=db.get(Document,v.document_id)
        db.execute(update(Document).where(Document.id==peer.id,Document.storage_revision==v.number).values(classification_status='pending'))
        evidence=dict(result['evidence']) if v.id==version.id else {}
        evidence.update(reason=reason,identity={'uuid':current['uuid'],'requires_review':True,'condition_hash':condition,
            'conflicting_versions':sorted(r['version_id'] for r in affected),'authority_validated':False})
        pending_rows=list(db.scalars(select(Review).where(Review.version_id==v.id,Review.status=='pending').order_by(Review.created_at.desc(),Review.id)))
        pending=next((r for r in pending_rows if r.evidence.get('identity',{}).get('condition_hash')==condition),pending_rows[0] if pending_rows else None)
        for other in pending_rows:
            if other is not pending:other.status='superseded'
        if pending and pending.evidence.get('identity',{}).get('condition_hash') not in (None,condition):
            # Preserve the previous conflict snapshot even if no human had resolved it yet.
            pending.status='superseded';pending=None
        if pending:
            pending.evidence={**pending.evidence,**evidence}
        else:
            links=[{'company_id':r.company_id,'role':r.role} for r in db.scalars(select(DocumentCompanyLink).where(DocumentCompanyLink.document_id==peer.id))]
            if peer.company_id:links.append({'company_id':peer.company_id,'role':'owner'})
            db.add(Review(document_id=peer.id,version_id=v.id,evidence=evidence,proposed_links=links))
        if v.id==version.id:result['evidence']=evidence;result['automatic']=False
        db.add(StorageEvent(actor_id=actor,action='identity_conflict_detected',document_id=peer.id,code=reason))
    db.flush()

def acknowledge(db,version,review,actor,reason):
    if not blocked(db,version.id):return
    condition=db.scalar(select(identities.c.condition_hash).where(identities.c.version_id==version.id))
    if review.evidence.get('identity',{}).get('condition_hash')!=condition:
        from .storage.providers import StorageError
        raise StorageError('revision_conflict')
    db.execute(update(identities).where(identities.c.version_id==version.id).values(requires_review=False,
        reviewed_by=actor.subject,reviewed_at=now(),review_id=review.id))
