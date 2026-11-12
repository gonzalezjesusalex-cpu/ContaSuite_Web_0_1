"""Transactional core. Actors must be created by trusted server code, never deserialized from API payloads.

HTTP derives actors from authenticated named sessions; internal workers use explicit technical identities.
"""
import hashlib
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select, update, delete
from ..models import (Company, Document, StorageSource, DocumentVersion, DocumentLocation,
                      DocumentCompanyLink, DocumentClassificationReview, StorageEvent, now)
from .internal import InternalStorageProvider, validate_payload
from .local import LocalFolderProvider
from .paths import safe_key
from .providers import StorageError
from .schemas import DocumentPublic, SourcePublic, VerifiedContent
from .settings import StorageSettings
from .smb import WindowsSMBProvider, windows_root
from .catalog import DocumentCatalog, validate_metadata
from .review import ClassificationService


@dataclass(frozen=True)
class StorageActor:
    subject: str
    company_ids: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    admin: bool = False
    write_company_ids: frozenset[str] | None = None

    def require(self, permission, company_id=None):
        if not self.subject or len(self.subject) > 100:
            raise StorageError('unauthenticated')
        if not self.admin and (permission not in self.permissions or
                               (company_id is not None and company_id not in self.company_ids)):
            raise StorageError('forbidden')
        if not self.admin and permission == 'write' and company_id is not None and company_id not in (
                self.company_ids if self.write_company_ids is None else self.write_company_ids):
            raise StorageError('forbidden')


class StorageService(DocumentCatalog, ClassificationService):
    def __init__(self, session_factory, settings: StorageSettings):
        self.sessions = session_factory
        self.settings = settings
        self.internal = InternalStorageProvider(settings.internal_root, max_file_bytes=settings.max_file_bytes)

    def _event(self, db, actor, action, *, document_id=None, source_id=None, company_id=None, outcome='success', code=None):
        db.add(StorageEvent(actor_id=actor.subject, action=action, document_id=document_id,
                            source_id=source_id, company_id=company_id, outcome=outcome, code=code))

    def _failure(self, actor, action, code):
        if actor.subject and len(actor.subject) <= 100:
            with self.sessions.begin() as db:
                self._event(db, actor, action, outcome='denied' if code in {'forbidden', 'not_found', 'unauthenticated'} else 'error', code=code)

    def _provider(self, source):
        if not source.enabled:
            raise StorageError('source_disabled')
        if source.kind == 'windows_smb':
            if not source.configuration.get('windows'):
                return WindowsSMBProvider()
            return self._smb(source.configuration['windows'], source.configuration.get('exclusions', []))
        if source.kind == 'internal':
            if source.id == 'cs_internal':
                return self.internal
            if source.id == 'cs_legacy':
                return LocalFolderProvider(self.settings.legacy_root, (self.settings.legacy_root,),
                                           max_file_bytes=self.settings.max_file_bytes, allow_legacy_public_cer=True)
            raise StorageError('invalid_configuration')
        if source.kind == 'local_folder':
            return self._local(Path(source.root_path), source.configuration.get('exclusions', []))
        raise StorageError('invalid_configuration')

    def _smb(self, windows, exclusions=()):
        return WindowsSMBProvider(windows_root(windows), self.settings.smb_allowed_roots,
                                  exclusions=exclusions, max_file_bytes=self.settings.max_file_bytes,
                                  max_entries=self.settings.max_scan_entries, max_seconds=self.settings.max_scan_seconds)

    def _local(self, root, exclusions=()):
        provider = LocalFolderProvider(root, self.settings.allowed_roots, exclusions=exclusions,
                                       max_file_bytes=self.settings.max_file_bytes,
                                       max_entries=self.settings.max_scan_entries, max_seconds=self.settings.max_scan_seconds)
        for internal in (self.settings.internal_root, self.settings.legacy_root):
            internal = internal.absolute()
            if provider.root.is_relative_to(internal) or internal.is_relative_to(provider.root):
                raise StorageError('repository_overlap')
        return provider

    def register_local(self, actor, label, root, *, exclusions=()):
        try:
            actor.require('manage_sources')
            if not label.strip() or len(label) > 160 or len(exclusions) > 100 or any(not isinstance(p, str) or len(p) > 200 for p in exclusions):
                raise StorageError('invalid_configuration')
            provider = self._local(Path(root), exclusions)
            available = provider.availability()
            if available.state != 'available':
                raise StorageError(available.code or 'root_unavailable')
            with self.sessions.begin() as db:
                source = StorageSource(id=str(uuid4()), label=label.strip(), kind='local_folder', root_path=str(provider.root),
                                       configuration={'exclusions': list(exclusions)})
                db.add(source)
                db.flush()
                self._event(db, actor, 'source_registered', source_id=source.id)
                result = SourcePublic(id=source.id, label=source.label, kind=source.kind, enabled=True, state='available')
            return result
        except StorageError as exc:
            self._failure(actor, 'source_register_failed', exc.code)
            raise

    def sources(self, actor):
        actor.require('manage_sources')
        with self.sessions() as db:
            result = []
            for source in db.scalars(select(StorageSource).order_by(StorageSource.label)):
                try:
                    status = self._provider(source).availability()
                    state, code = status.state, status.code
                except StorageError as exc:
                    state, code = 'unavailable', exc.code
                result.append(SourcePublic(id=source.id, label=source.label, kind=source.kind, enabled=source.enabled, state=state, code=code))
            return result

    def _companies(self, db, doc):
        companies = set(db.scalars(select(DocumentCompanyLink.company_id).where(DocumentCompanyLink.document_id == doc.id)))
        if doc.company_id:
            companies.add(doc.company_id)
        return companies

    def _document(self, db, actor, ident, permission='read'):
        actor.require(permission)
        doc = db.get(Document, ident)
        if doc is None:
            raise StorageError('not_found')
        companies = self._companies(db, doc)
        if not actor.admin:
            if doc.storage_revision > 1 and doc.classification_status == 'pending':
                raise StorageError('not_found')
            if companies and not (companies & actor.company_ids):
                raise StorageError('not_found')
            if not companies and 'review' not in actor.permissions:
                raise StorageError('not_found')
            if permission == 'write':
                writable = actor.company_ids if actor.write_company_ids is None else actor.write_company_ids
                if not companies or not companies.issubset(writable):
                    raise StorageError('forbidden')
        return doc

    def _public(self, db, doc, actor):
        return DocumentPublic(id=doc.id, name=doc.name, size=doc.size, revision=doc.storage_revision,
                              company_ids=sorted(self._companies(db, doc) if actor.admin else self._companies(db, doc) & actor.company_ids), document_type=doc.document_type, period=doc.period,
                              classification_status=doc.classification_status, created_at=doc.created_at)

    def document(self, actor, ident):
        try:
            with self.sessions.begin() as db:
                doc = self._document(db, actor, ident)
                self._event(db, actor, 'metadata_read', document_id=doc.id)
                result = self._public(db, doc, actor)
            return result
        except StorageError as exc:
            self._failure(actor, 'metadata_read_failed', exc.code)
            raise

    def _version(self, db, actor, doc, stored, source_id, key, *, mtime_ns=None):
        version = DocumentVersion(id=str(uuid4()), document_id=doc.id, number=doc.storage_revision,
                                  original_name=doc.name, sha256=stored.sha256, size=stored.size,
                                  media_type=stored.media_type, file_metadata={}, created_by=actor.subject)
        db.add(version)
        db.flush()
        db.add(DocumentLocation(version_id=version.id, source_id=source_id, relative_key=key,
                                key_digest=hashlib.sha256(key.casefold().encode()).hexdigest(), availability='available',
                                size=stored.size, mtime_ns=str(mtime_ns) if mtime_ns is not None else None, last_seen_at=now()))
        if doc.classification_status == 'pending':
            db.add(DocumentClassificationReview(document_id=doc.id, version_id=version.id, evidence={}, proposed_links=[]))
        return version

    def upload(self, actor, stream, name, *, company_id=None, document_id=None, expected_revision=None, category='General', document_type='unknown', period=None):
        stored = None
        try:
            actor.require('write', company_id)
            validate_metadata(category, document_type, period)
            if not company_id and not document_id:
                actor.require('review')
            # Authorize before consuming or storing the payload.
            with self.sessions() as db:
                if document_id:
                    existing = self._document(db, actor, document_id, 'write')
                    if company_id and company_id not in self._companies(db, existing):
                        raise StorageError('classification_conflict')
                    if not existing.managed or expected_revision is None:
                        raise StorageError('revision_conflict')
                elif company_id and db.get(Company, company_id) is None:
                    raise StorageError('not_found')
            stored = self.internal.put(stream, name)
            with self.sessions.begin() as db:
                from ..document_identity import lock,register,available
                lock(db)
                source = db.get(StorageSource, 'cs_internal')
                if source is None or not source.enabled:
                    raise StorageError('source_disabled')
                if document_id:
                    doc = self._document(db, actor, document_id, 'write')
                    changed = db.execute(update(Document).where(Document.id == doc.id, Document.storage_revision == expected_revision)
                                         .values(storage_revision=expected_revision + 1, name=name, size=stored.size, category=category, document_type=document_type, period=period))
                    if not changed.rowcount:
                        raise StorageError('revision_conflict')
                    db.refresh(doc)
                else:
                    doc = Document(id=str(uuid4()), company_id=company_id, name=name, category=category, document_type=document_type, period=period, size=stored.size,
                                   storage_name=None, managed=True, storage_revision=1,
                                   classification_status='confirmed' if company_id else 'pending')
                    db.add(doc)
                    db.flush()
                    if company_id:
                        db.add(DocumentCompanyLink(document_id=doc.id, company_id=company_id, role='owner', method='manual', confirmed_by=actor.subject))
                version=self._version(db, actor, doc, stored, 'cs_internal', stored.key)
                if name.lower().endswith('.xml') and available(db):
                    from .classifier import classify
                    with self.internal.open_read(stored.key) as content:identity=classify(content,name,[])
                    db.flush();register(db,doc,version,identity,actor.subject)
                self._event(db, actor, 'version_uploaded', document_id=doc.id, source_id='cs_internal', company_id=doc.company_id)
                result = self._public(db, doc, actor)
            return result
        except Exception as exc:
            if stored:
                self.internal.discard(stored.key)
            code = exc.code if isinstance(exc, StorageError) else 'storage_error'
            self._failure(actor, 'upload_failed', code)
            if isinstance(exc, StorageError):
                raise
            raise StorageError(code) from None

    def _buffer(self, provider, key):
        spool = tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024, mode='w+b')
        try:
            digest = hashlib.sha256()
            size = 0
            with provider.open_read(key) as reader:
                while chunk := reader.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.settings.max_file_bytes:
                        raise StorageError('file_too_large')
                    digest.update(chunk)
                    spool.write(chunk)
            spool.seek(0)
            return spool, size, digest.hexdigest()
        except Exception:
            spool.close()
            raise

    def observe_external(self, actor, source_id, key, *, company_id=None, lease=None):
        """Register one observation; LocalIndexer coordinates recursive jobs and classification."""
        actor.require('index', company_id)
        if company_id is None:
            actor.require('review')
        safe_key(key)
        digest_key = hashlib.sha256(key.casefold().encode()).hexdigest()
        try:
            with self.sessions.begin() as db:
                from ..document_identity import lock
                lock(db)
                source = db.get(StorageSource, source_id)
                if not source or source.kind not in {'local_folder', 'windows_smb'}:
                    raise StorageError('source_not_found')
                if company_id and not db.get(Company, company_id):
                    raise StorageError('not_found')
                provider = self._provider(source)
                # Serialize observations for one source on SQLite and PostgreSQL.
                db.execute(update(StorageSource).where(StorageSource.id == source_id).values(label=source.label))
                if lease:
                    from .indexer import check_lease
                    check_lease(db, *lease)
                spool, size, digest = self._buffer(provider, key)
                try:
                    media_type = validate_payload(spool, Path(key).name, allow_public_cer=True)
                    from .classifier import classify
                    identity=classify(spool,Path(key).name,[]) if Path(key).suffix.lower()=='.xml' else None
                finally:
                    spool.close()
                previous = db.scalar(select(DocumentVersion).join(DocumentLocation, DocumentLocation.version_id == DocumentVersion.id)
                                     .where(DocumentLocation.source_id == source_id, DocumentLocation.key_digest == digest_key)
                                     .order_by(DocumentVersion.number.desc()))
                if previous:
                    doc = self._document(db, actor, previous.document_id, 'index')
                    if company_id and company_id not in self._companies(db, doc):
                        raise StorageError('classification_conflict')
                    if previous.sha256 == digest:
                        db.execute(update(DocumentLocation).where(DocumentLocation.version_id == previous.id,
                                   DocumentLocation.source_id == source_id, DocumentLocation.key_digest == digest_key)
                                   .values(availability='available', last_seen_at=now(), error_code=None,
                                           mtime_ns=str(provider.metadata(key).mtime_ns)))
                        self._event(db, actor, 'observation_unchanged', document_id=doc.id, source_id=source_id)
                        return self._public(db, doc, actor)
                    changed = db.execute(update(Document).where(Document.id == doc.id, Document.storage_revision == previous.number)
                                         .values(storage_revision=previous.number + 1, size=size, classification_status='pending',
                                                 document_type='unknown', period=None))
                    if not changed.rowcount:
                        raise StorageError('revision_conflict')
                    db.refresh(doc)
                    # Do not expose new bytes through an automatic link inferred from an older version.
                    db.execute(delete(DocumentCompanyLink).where(DocumentCompanyLink.document_id == doc.id,
                                                                 DocumentCompanyLink.method == 'rfc-v1'))
                    db.execute(update(DocumentLocation).where(DocumentLocation.source_id == source_id, DocumentLocation.key_digest == digest_key)
                               .values(availability='superseded'))
                else:
                    doc = Document(id=str(uuid4()), company_id=company_id, name=Path(key).name, category='General', size=size,
                                   managed=True, storage_revision=1, classification_status='confirmed' if company_id else 'pending')
                    db.add(doc)
                    db.flush()
                    if company_id:
                        db.add(DocumentCompanyLink(document_id=doc.id, company_id=company_id, role='owner', method='manual', confirmed_by=actor.subject))
                from .providers import StoredFile
                version=self._version(db, actor, doc, StoredFile(key, size, digest, media_type), source_id, key, mtime_ns=provider.metadata(key).mtime_ns)
                if identity:
                    from ..document_identity import lock,register
                    lock(db);db.flush();register(db,doc,version,identity,actor.subject)
                self._event(db, actor, 'external_observed', document_id=doc.id, source_id=source_id)
                result = self._public(db, doc, actor)
            return result
        except StorageError as exc:
            self._failure(actor, 'observation_failed', exc.code)
            raise

    @contextmanager
    def read(self, actor, ident, *, revision=None):
        spool = None
        unavailable = []
        try:
            with self.sessions.begin() as db:
                doc = self._document(db, actor, ident)
                version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id,
                                    DocumentVersion.number == (revision if revision is not None else doc.storage_revision)))
                if version is None:
                    raise StorageError('not_found')
                locations = db.scalars(select(DocumentLocation).where(DocumentLocation.version_id == version.id,
                                      DocumentLocation.availability != 'superseded')).all()
                if not locations:
                    raise StorageError('unavailable')
                failure = 'unavailable'
                for location in locations:
                    try:
                        source = db.get(StorageSource, location.source_id)
                        spool, size, digest = self._buffer(self._provider(source), location.relative_key)
                        if version.sha256 is None:
                            # Legacy fingerprints were deliberately not invented by migration.
                            spool.close()
                            spool = None
                            raise StorageError('legacy_verification_required')
                        if digest != version.sha256 or size != version.size:
                            spool.close()
                            spool = None
                            raise StorageError('integrity_error')
                        location.availability = 'available'
                        location.error_code = None
                        location.last_seen_at = now()
                        break
                    except StorageError as exc:
                        failure = exc.code
                        state = {'missing': 'missing', 'access_denied': 'denied', 'integrity_error': 'changed',
                                 'legacy_verification_required': 'unchecked'}.get(exc.code, 'unavailable')
                        unavailable.append((location.id, state, exc.code))
                for location_id, state, code in unavailable:
                    db.execute(update(DocumentLocation).where(DocumentLocation.id == location_id).values(availability=state, error_code=code))
                if spool is None:
                    raise StorageError(failure)
                self._event(db, actor, 'content_read', document_id=doc.id)
                result = VerifiedContent(self._public(db, doc, actor), version.media_type, spool, version.original_name)
            yield result
        except StorageError as exc:
            if unavailable:
                # The failed read transaction rolled back; preserve observations in a separate transaction.
                with self.sessions.begin() as db:
                    for location_id, state, code in unavailable:
                        db.execute(update(DocumentLocation).where(DocumentLocation.id == location_id).values(availability=state, error_code=code))
            self._failure(actor, 'content_read_failed', exc.code)
            raise
        finally:
            if spool:
                spool.close()
