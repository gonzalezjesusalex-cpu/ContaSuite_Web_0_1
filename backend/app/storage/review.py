"""Version-bound classification proposals and audited human decisions."""
from sqlalchemy import select, update, delete
from ..models import (Company, Document, DocumentVersion, DocumentCompanyLink,
                      DocumentClassificationReview as Review, now)
from .providers import StorageError


class ClassificationService:
    def reopen_review(self,actor,ident,review_id,revision,reason):
        actor.require('review')
        if not actor.admin or not reason or len(reason.strip())<3:raise StorageError('forbidden' if not actor.admin else 'invalid_metadata')
        from ..document_identity import lock,blocked
        with self.sessions.begin() as db:
            lock(db);doc=self._document(db,actor,ident,'review')
            if doc.storage_revision!=revision:raise StorageError('revision_conflict')
            old=db.get(Review,review_id);version=db.get(DocumentVersion,old.version_id) if old else None
            if not old or old.document_id!=ident or not version or version.number!=revision or old.status!='resolved' or old.resolution!='reject' or not blocked(db,version.id):raise StorageError('revision_conflict')
            pending=db.scalar(select(Review).where(Review.version_id==version.id,Review.status=='pending'))
            if pending:return {'review_id':pending.id,'idempotent':True}
            reopened=Review(document_id=ident,version_id=version.id,evidence={**old.evidence,'reopened_from':old.id,
                'reopened_by':actor.subject,'reopened_at':now().isoformat(),'reopen_reason':reason.strip()},proposed_links=old.proposed_links)
            db.add(reopened);db.flush();doc.classification_status='pending'
            self._event(db,actor,'classification_reopened',document_id=ident)
            return {'review_id':reopened.id,'idempotent':False}

    def duplicates(self, actor, ident):
        with self.sessions() as db:
            doc = self._document(db, actor, ident)
            digest = db.scalar(select(DocumentVersion.sha256).where(DocumentVersion.document_id == ident,
                                                                      DocumentVersion.number == doc.storage_revision))
            if not digest:
                return []
            rows = db.scalars(select(Document).join(DocumentVersion, DocumentVersion.document_id == Document.id)
                .where(Document.id != ident, DocumentVersion.sha256 == digest,
                       DocumentVersion.number == Document.storage_revision, self._scope(actor))
                .order_by(Document.id).limit(20))
            return [{'id': d.id, 'name': d.name} for d in rows]

    def reviews(self, actor, ident):
        actor.require('review')
        if not actor.admin:
            raise StorageError('forbidden')
        with self.sessions() as db:
            doc = self._document(db, actor, ident)
            rows = db.scalars(select(Review).where(Review.document_id == ident).order_by(Review.created_at.desc()).limit(50))
            return [{'id': r.id, 'version': db.get(DocumentVersion, r.version_id).number,
                     'status': r.status, 'evidence': r.evidence, 'proposed_links': r.proposed_links,
                     'resolved_by': r.resolved_by, 'resolution': r.resolution,
                     'current': db.get(DocumentVersion, r.version_id).number == doc.storage_revision}
                    for r in rows]

    def apply_classification(self, actor, ident, revision, result, *, lease=None):
        actor.require('review')
        # Automatic changes require global indexing authority, never inferred from user input.
        if not actor.admin:
            raise StorageError('forbidden')
        with self.sessions.begin() as db:
            from ..document_identity import lock,register,blocked
            lock(db)
            if lease:
                from .indexer import check_lease
                check_lease(db, *lease)
            doc = self._document(db, actor, ident, 'index')
            changed = db.execute(update(Document).where(Document.id == ident, Document.storage_revision == revision)
                                 .values(classification_status=doc.classification_status))
            if not changed.rowcount:
                raise StorageError('revision_conflict')
            version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == ident, DocumentVersion.number == revision))
            register(db,doc,version,result,actor.subject)
            review = db.scalar(select(Review).where(Review.version_id == version.id, Review.status == 'pending'))
            if review is None:
                # A human already resolved this version. A resumed worker must preserve that decision.
                previous = db.scalar(select(Review).where(Review.version_id == version.id)
                                     .order_by(Review.created_at.desc()))
                if previous:
                    if previous.resolution != 'automatic' or previous.evidence.get('catalog_digest') == result['evidence'].get('catalog_digest'):
                        return
                    previous.status = 'superseded'
                review = Review(document_id=ident, version_id=version.id)
                db.add(review)
            db.execute(update(Review).where(Review.document_id == ident, Review.version_id != version.id,
                                           Review.status == 'pending').values(status='superseded'))
            review.evidence = {**review.evidence,**result['evidence']}
            review.proposed_links = result['links']
            existing = db.scalars(select(DocumentCompanyLink).where(DocumentCompanyLink.document_id == ident)).all()
            existing_ids = self._companies(db, doc)
            proposed_ids = {l['company_id'] for l in result['links']}
            manual = doc.company_id is not None or any(l.method != 'rfc-v1' for l in existing)
            automatic = result['automatic'] and not blocked(db,version.id) and (not existing_ids or existing_ids == proposed_ids)
            if manual:
                automatic = False
                if not blocked(db,version.id):review.evidence = {**review.evidence, 'reason': 'existing_assignment'}
            doc.document_type = result['type'] if doc.document_type == 'unknown' else doc.document_type
            if doc.period is None:
                doc.period = result['period']
            doc.classification_status = 'pending'
            if not automatic and not manual:
                db.execute(delete(DocumentCompanyLink).where(DocumentCompanyLink.document_id == ident,
                                                             DocumentCompanyLink.method == 'rfc-v1'))
            if automatic:
                db.execute(delete(DocumentCompanyLink).where(DocumentCompanyLink.document_id == ident))
                for link in result['links']:
                    db.add(DocumentCompanyLink(document_id=ident, **link, method='rfc-v1', confirmed_by=actor.subject))
                doc.classification_status = 'confirmed'
                review.status, review.resolution = 'resolved', 'automatic'
                review.resolved_by, review.resolved_at = actor.subject, now()
            self._event(db, actor, 'classification_automatic' if automatic else 'classification_proposed', document_id=ident)

    def resolve_review(self, actor, ident, review_id, revision, action, links, reason=None):
        actor.require('review')
        if action not in {'confirm', 'correct', 'reject'} or len(links) > 20:
            raise StorageError('invalid_metadata')
        try:
            with self.sessions.begin() as db:
                from ..document_identity import lock,blocked,acknowledge
                lock(db)
                doc = self._document(db, actor, ident, 'review')
                changed = db.execute(update(Document).where(Document.id == ident, Document.storage_revision == revision)
                                     .values(classification_status=doc.classification_status))
                if not changed.rowcount:
                    raise StorageError('revision_conflict')
                review = db.get(Review, review_id)
                version = db.get(DocumentVersion, review.version_id) if review else None
                if not review or review.document_id != ident or review.status != 'pending' or version.number != revision:
                    raise StorageError('revision_conflict')
                if blocked(db,version.id) and (not reason or len(reason.strip())<3):raise StorageError('invalid_metadata')
                chosen = review.proposed_links if action == 'confirm' else links if action == 'correct' else []
                before_links=sorted(self._companies(db,doc))
                if action != 'reject' and not chosen:
                    raise StorageError('invalid_metadata')
                normalized = set()
                # Changing relationships requires permission for every old and new company.
                for company in self._companies(db, doc):
                    actor.require('review', company)
                for link in chosen:
                    cid, role = link.get('company_id'), link.get('role')
                    if role not in {'owner', 'issuer', 'receiver'} or not db.get(Company, cid):
                        raise StorageError('invalid_metadata')
                    actor.require('review', cid)
                    normalized.add((cid, role))
                if action != 'reject':
                    acknowledge(db,version,review,actor,reason)
                    db.execute(delete(DocumentCompanyLink).where(DocumentCompanyLink.document_id == ident))
                    doc.company_id = None
                    for cid, role in sorted(normalized):
                        db.add(DocumentCompanyLink(document_id=ident, company_id=cid, role=role,
                                                   method='manual', confirmed_by=actor.subject))
                    doc.classification_status = 'confirmed'
                else:
                    # Reject the proposal, preserving any previously confirmed ownership.
                    doc.classification_status = 'confirmed' if self._companies(db, doc) else 'rejected'
                review.status, review.resolution = 'resolved', action
                review.resolved_by, review.resolved_at = actor.subject, now()
                review.evidence={**review.evidence,'human_decision':{'actor':actor.subject,'at':now().isoformat(),
                    'reason':reason or '', 'links':sorted(normalized),'before_links':before_links}}
                self._event(db, actor, 'classification_' + action, document_id=ident)
        except StorageError as exc:
            self._failure(actor, 'classification_failed', exc.code)
            raise
