"""Paginated public catalog and non-destructive verification of legacy attachments."""
import re
import hashlib
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select, update, func, or_, and_, exists
from ..models import (Company, Document, DocumentVersion, DocumentLocation, DocumentCompanyLink,
                      StorageSource, now)
from .internal import validate_payload
from .providers import StorageError
from .schemas import (CatalogDocument, CatalogPage, CompanyPublic, LocationPublic, DocumentDetail, VersionPublic)

DOCUMENT_TYPES = {'unknown', 'cfdi', 'declaration', 'acknowledgement', 'certificate', 'other'}


def validate_metadata(category, document_type, period):
    if not category.strip() or len(category) > 80 or re.search(r'[\x00-\x1f]', category):
        raise StorageError('invalid_metadata')
    if document_type not in DOCUMENT_TYPES or (period and not re.fullmatch(r'(20\d{2}|2100)-(0[1-9]|1[0-2])', period)):
        raise StorageError('invalid_metadata')


class DocumentCatalog:
    def _scope(self, actor):
        linked = exists(select(DocumentCompanyLink.document_id).where(DocumentCompanyLink.document_id == Document.id).correlate(Document))
        if actor.admin:
            return True
        permitted = exists(select(DocumentCompanyLink.document_id).where(DocumentCompanyLink.document_id == Document.id,
                                                                         DocumentCompanyLink.company_id.in_(actor.company_ids)).correlate(Document))
        result = or_(Document.company_id.in_(actor.company_ids), permitted)
        if 'review' in actor.permissions:
            result = or_(result, and_(Document.company_id.is_(None), ~linked))
        return and_(result, or_(Document.storage_revision <= 1, Document.classification_status != 'pending'))

    def _catalog_rows(self, db, actor, docs):
        if not docs:
            return []
        ids = [d.id for d in docs]
        by_doc = {d.id: set() for d in docs}
        for d in docs:
            if d.company_id:
                by_doc[d.id].add(d.company_id)
        for doc_id, company_id in db.execute(select(DocumentCompanyLink.document_id, DocumentCompanyLink.company_id)
                                             .where(DocumentCompanyLink.document_id.in_(ids))):
            by_doc[doc_id].add(company_id)
        if not actor.admin:
            by_doc = {k: values & actor.company_ids for k, values in by_doc.items()}
        company_ids = set().union(*by_doc.values())
        companies = {c.id: CompanyPublic(id=c.id, name=c.name, rfc=c.rfc) for c in db.scalars(select(Company).where(Company.id.in_(company_ids)))}
        source_rows = db.execute(select(DocumentVersion.document_id, DocumentLocation, StorageSource)
                         .join(DocumentLocation, DocumentLocation.version_id == DocumentVersion.id)
                         .join(StorageSource, StorageSource.id == DocumentLocation.source_id)
                         .join(Document, Document.id == DocumentVersion.document_id)
                         .where(Document.id.in_(ids), DocumentVersion.number == Document.storage_revision)).all()
        sources = {i: [] for i in ids}
        for ident, location, source in source_rows:
            sources[ident].append(LocationPublic(source_id=source.id, label=source.label, kind=source.kind,
                availability=location.availability if source.enabled else 'unavailable',
                last_seen_at=location.last_seen_at, error_code=location.error_code if source.enabled else 'source_disabled'))
        result = []
        for doc in docs:
            locations = sources[doc.id]
            if not locations and doc.storage_name and not doc.managed:
                locations = [LocationPublic(source_id='cs_legacy', label='Adjuntos anteriores', kind='internal', availability='unchecked')]
            states = {s.availability for s in locations}
            availability = next((s for s in ('available', 'unchecked', 'changed', 'missing', 'denied', 'unavailable') if s in states), 'unavailable')
            result.append(CatalogDocument(id=doc.id, name=doc.name, size=doc.size, revision=doc.storage_revision,
                company_ids=sorted(by_doc[doc.id]), companies=[companies[c] for c in sorted(by_doc[doc.id]) if c in companies],
                document_type=doc.document_type, period=doc.period, classification_status=doc.classification_status,
                created_at=doc.created_at, category=doc.category, format=Path(doc.name).suffix.lower().lstrip('.'),
                sources=locations, availability=availability))
        return result

    def list_documents(self, actor, *, query='', company_id=None, period=None, year=None, month=None,
                       format=None, document_type=None, source_id=None, pending=False, offset=0, limit=25):
        try:
            actor.require('read', company_id)
            if not 1 <= limit <= 100 or not 0 <= offset <= 100000 or len(query) > 200:
                raise StorageError('invalid_filters')
            if year is not None and not 2000 <= year <= 2100 or month is not None and not 1 <= month <= 12:
                raise StorageError('invalid_filters')
            if format and format not in {'pdf', 'xml', 'cer'} or document_type and document_type not in DOCUMENT_TYPES:
                raise StorageError('invalid_filters')
            with self.sessions.begin() as db:
                if company_id and db.get(Company, company_id) is None:
                    raise StorageError('not_found')
                conditions = [self._scope(actor)]
                if company_id:
                    conditions.append(or_(Document.company_id == company_id, exists(select(DocumentCompanyLink.document_id)
                        .where(DocumentCompanyLink.document_id == Document.id, DocumentCompanyLink.company_id == company_id))))
                if query:
                    escaped = query.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
                    match = '%' + escaped + '%'
                    company_match = select(Company.id).where(or_(Company.name.ilike(match, escape='\\'), Company.rfc.ilike(match, escape='\\')),
                        or_(Company.id == Document.company_id, exists(select(DocumentCompanyLink.company_id)
                            .where(DocumentCompanyLink.document_id == Document.id, DocumentCompanyLink.company_id == Company.id)
                            .correlate(Document, Company)))).correlate(Document)
                    if not actor.admin:
                        company_match = company_match.where(Company.id.in_(actor.company_ids))
                    conditions.append(or_(Document.name.ilike(match, escape='\\'), Document.period.ilike(match, escape='\\'), exists(company_match)))
                if period:
                    if not re.fullmatch(r'(20\d{2}|2100)-(0[1-9]|1[0-2])', period):
                        raise StorageError('invalid_filters')
                    conditions.append(Document.period == period)
                if year is not None:
                    conditions.append(func.substr(Document.period, 1, 4) == str(year))
                if month is not None:
                    conditions.append(func.substr(Document.period, 6, 2) == f'{month:02d}')
                if format:
                    conditions.append(func.lower(Document.name).like('%.' + format))
                if document_type:
                    conditions.append(Document.document_type == document_type)
                if source_id:
                    located = exists(select(DocumentLocation.id).join(DocumentVersion, DocumentVersion.id == DocumentLocation.version_id)
                        .where(DocumentVersion.document_id == Document.id, DocumentVersion.number == Document.storage_revision,
                               DocumentLocation.source_id == source_id))
                    conditions.append(or_(located, and_(Document.storage_name.isnot(None), Document.managed == False, Document.storage_revision == 0))
                                      if source_id == 'cs_legacy' else located)
                pending_count = db.scalar(select(func.count()).select_from(Document).where(*conditions, Document.classification_status == 'pending'))
                if pending:
                    actor.require('review')
                    conditions.append(Document.classification_status == 'pending')
                total = db.scalar(select(func.count()).select_from(Document).where(*conditions))
                docs = db.scalars(select(Document).where(*conditions).order_by(Document.created_at.desc(), Document.id)
                                  .offset(offset).limit(limit)).all()
                result = CatalogPage(items=self._catalog_rows(db, actor, docs), total=total, pending_count=pending_count, offset=offset, limit=limit)
                self._event(db, actor, 'catalog_read', company_id=company_id)
            return result
        except StorageError as exc:
            self._failure(actor, 'catalog_read_failed', exc.code)
            raise

    def describe(self, actor, ident):
        try:
            with self.sessions.begin() as db:
                doc = self._document(db, actor, ident)
                versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == ident).order_by(DocumentVersion.number.desc())).all()
                result = DocumentDetail(document=self._catalog_rows(db, actor, [doc])[0], versions=[VersionPublic(
                    number=v.number, original_name=v.original_name, sha256=v.sha256, size=v.size,
                    media_type=v.media_type, created_at=v.created_at) for v in versions])
                self._event(db, actor, 'catalog_detail_read', document_id=ident)
            return result
        except StorageError as exc:
            self._failure(actor, 'catalog_detail_failed', exc.code)
            raise

    def verify_legacy(self, actor, ident):
        """Verify or adopt one attachment, retaining its ID and physical file. No filesystem writes."""
        try:
            with self.sessions.begin() as db:
                doc = self._document(db, actor, ident)
                if doc.managed or not doc.storage_name:
                    return
                # Serialize first verification of a legacy attachment on both supported databases.
                db.execute(update(Document).where(Document.id == ident).values(name=doc.name))
                db.refresh(doc)
                version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == ident,
                                                                   DocumentVersion.number == max(1, doc.storage_revision)))
                if version and version.sha256:
                    return
                source = db.get(StorageSource, 'cs_legacy')
                if source is None:
                    raise StorageError('source_not_found')
                provider = self._provider(source)
                buffer, size, digest = self._buffer(provider, doc.storage_name)
                try:
                    media_type = validate_payload(buffer, doc.name, allow_public_cer=True)
                finally:
                    buffer.close()
                if size != doc.size:
                    raise StorageError('file_changed')
                if version is None:
                    version = DocumentVersion(id=str(uuid4()), document_id=ident, number=1, original_name=doc.name,
                        size=size, media_type=media_type, sha256=digest, file_metadata={'legacy': True}, created_by=actor.subject)
                    db.add(version)
                    db.flush()
                    db.add(DocumentLocation(version_id=version.id, source_id=source.id, relative_key=doc.storage_name,
                        key_digest=hashlib.sha256(doc.storage_name.casefold().encode()).hexdigest(),
                        size=size, availability='available', last_seen_at=now()))
                    doc.storage_revision = 1
                else:
                    version.sha256 = digest
                    version.media_type = media_type
                    db.execute(update(DocumentLocation).where(DocumentLocation.version_id == version.id, DocumentLocation.source_id == source.id)
                               .values(availability='available', error_code=None, last_seen_at=now()))
                version.file_metadata = {'legacy': True, 'verified_by': actor.subject, 'verified_at': now().isoformat()}
                if doc.company_id and not db.scalar(select(DocumentCompanyLink.document_id).where(DocumentCompanyLink.document_id == ident,
                                                                                                  DocumentCompanyLink.company_id == doc.company_id)):
                    db.add(DocumentCompanyLink(document_id=ident, company_id=doc.company_id, role='owner', method='legacy', confirmed_by=actor.subject))
                doc.classification_status = 'confirmed' if doc.company_id else 'pending'
                self._event(db, actor, 'legacy_verified', document_id=ident, source_id=source.id)
        except StorageError as exc:
            self._failure(actor, 'legacy_verification_failed', exc.code)
            raise
