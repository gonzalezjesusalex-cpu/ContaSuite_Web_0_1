"""Admin-only local/SMB configuration and read-only connectivity checks."""
import re
from datetime import timedelta
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select, update, func
from ..models import (StorageSource, StorageIndexJob, StorageEvent, StorageWorkerState,
                      DocumentLocation, DocumentVersion, Document, now)
from ..security import utc
from .paths import safe_key
from .providers import StorageError


class ConnectorService:
    def __init__(self, service):
        self.service = service

    def authorize(self, actor):
        actor.require('manage_sources')
        if not actor.admin:
            raise StorageError('forbidden')

    def options(self, actor):
        self.authorize(actor)
        return {'allowed_roots': [str(p) for p in self.service.settings.allowed_roots],
                'max_scan_entries': self.service.settings.max_scan_entries,
                'max_scan_seconds': self.service.settings.max_scan_seconds,
                'max_file_bytes': self.service.settings.max_file_bytes,
                'smb_allowed_roots': [str(p) for p in self.service.settings.smb_allowed_roots],
                'smb_state': 'configured' if self.service.settings.smb_allowed_roots else 'pending_configuration'}

    def list(self, actor):
        self.authorize(actor)
        with self.service.sessions() as db:
            result = []
            for source in db.scalars(select(StorageSource).order_by(StorageSource.label)):
                last = db.scalar(select(StorageIndexJob).where(StorageIndexJob.source_id == source.id)
                                 .order_by(StorageIndexJob.created_at.desc()).limit(1))
                count = db.scalar(select(func.count(func.distinct(Document.id))).join(DocumentVersion,
                    DocumentVersion.document_id == Document.id).join(DocumentLocation, DocumentLocation.version_id == DocumentVersion.id)
                    .where(DocumentLocation.source_id == source.id, DocumentVersion.number == Document.storage_revision))
                errors = db.scalars(select(StorageEvent).where(StorageEvent.source_id == source.id,
                    StorageEvent.outcome.in_(['error','partial'])).order_by(StorageEvent.created_at.desc()).limit(5))
                result.append(dict(id=source.id,label=source.label,kind=source.kind,enabled=source.enabled,
                    root_path=source.root_path if source.kind == 'local_folder' else '',
                    revision=source.revision,interval_minutes=source.interval_minutes,next_scan_at=source.next_scan_at,
                    exclusions=source.configuration.get('exclusions', []), windows=source.configuration.get('windows', {}),
                    checked_at=source.checked_at,state=source.check_state,code=source.check_code,
                    document_count=count,last_job=None if not last else dict(id=last.id,status=last.status,
                        counters=last.counters,completed_at=last.completed_at,created_at=last.created_at,error_code=last.error_code),
                    recent_errors=[dict(code=e.code,created_at=e.created_at) for e in errors]))
            heartbeat = db.get(StorageWorkerState, 'indexer')
            return {'sources':result, 'worker':{'online': bool(heartbeat and utc(heartbeat.heartbeat_at)+timedelta(seconds=180)>now()),
                                              'last_seen_at':heartbeat.heartbeat_at if heartbeat else None}}

    def save(self, actor, payload, ident=None):
        self.authorize(actor)
        if not payload.label.strip() or any(ord(c)<32 for c in payload.label):
            raise StorageError('invalid_configuration')
        if payload.interval_minutes and not 5 <= payload.interval_minutes <= 10080:
            raise StorageError('invalid_configuration')
        if payload.kind == 'local_folder':
            if ident and not payload.enabled:
                # Revoking a source remains possible after its root is removed from the allowlist.
                # The immutable-root check below prevents replacing its locator with another path.
                root=payload.root_path
            else:
                provider = self.service._local(Path(payload.root_path), payload.exclusions)
                root = str(provider.root)
            configuration = {'exclusions':payload.exclusions}
        else:
            windows = payload.windows.model_dump()
            from .smb import windows_root
            windows['subdirectory'] = windows['subdirectory'].replace('\\', '/')
            windows_root(windows)
            if payload.enabled:
                self.service._smb(windows, payload.exclusions)
            if windows['subdirectory']:
                safe_key(windows['subdirectory'])
            if any(ord(c)<32 for c in windows['account_name']):
                raise StorageError('invalid_configuration')
            root = None
            configuration = {'exclusions':payload.exclusions,'windows':windows}
        with self.service.sessions.begin() as db:
            db.execute(update(StorageSource).where(StorageSource.id=='cs_internal').values(label=StorageSource.label))
            if ident:
                source = db.get(StorageSource, ident)
                if source is None:
                    raise StorageError('source_not_found')
                db.execute(update(StorageSource).where(StorageSource.id == ident).values(label=StorageSource.label))
                db.refresh(source)
                if source.kind == 'internal' or payload.kind != source.kind or source.root_path != root:
                    raise StorageError('immutable_source')
                if source.kind == 'windows_smb':
                    from .smb import windows_root
                    if windows_root(source.configuration.get('windows', {})) != windows_root(windows):
                        raise StorageError('immutable_source')
                if db.scalar(select(StorageIndexJob.id).where(StorageIndexJob.source_id == ident,
                              StorageIndexJob.status.in_(['queued','running']))):
                    raise StorageError('source_busy')
                if source.revision != payload.revision:
                    raise StorageError('revision_conflict')
                source.revision += 1
            else:
                for existing in db.scalars(select(StorageSource).where(StorageSource.kind == payload.kind)):
                    if (payload.kind == 'local_folder' and existing.root_path.lower() == root.lower()) or (
                            payload.kind == 'windows_smb' and windows_root(existing.configuration.get('windows', {})) == windows_root(windows)):
                        raise StorageError('duplicate_source')
                source = StorageSource(id=str(uuid4()),kind=payload.kind,root_path=root)
                db.add(source)
            source.label, source.enabled, source.configuration = payload.label.strip(), payload.enabled, configuration
            source.interval_minutes = payload.interval_minutes
            source.next_scan_at = now()+timedelta(minutes=payload.interval_minutes) if payload.enabled and payload.interval_minutes else None
            source.checked_at,source.check_state,source.check_code = None,'unchecked',None
            if payload.kind == 'windows_smb' and not payload.enabled:
                source.check_state,source.check_code = 'pending_configuration','smb_not_configured'
            db.flush()
            self.service._event(db, actor, 'source_updated' if ident else 'source_registered',source_id=source.id)
            return {'id':source.id,'revision':source.revision}

    def probe(self, actor, ident):
        self.authorize(actor)
        with self.service.sessions() as db:
            source = db.get(StorageSource, ident)
            if source is None:
                raise StorageError('source_not_found')
            revision = source.revision
            try:
                availability = self.service._provider(source).availability()
                state,code = availability.state,availability.code
            except StorageError as exc:
                state,code = 'unavailable',exc.code
            # A disabled SMB draft remains pending without any network operation.
            if source.kind == 'windows_smb' and not source.enabled:
                state,code = 'pending_configuration','smb_not_configured'
        with self.service.sessions.begin() as db:
            changed = db.execute(update(StorageSource).where(StorageSource.id == ident,StorageSource.revision == revision)
                .values(checked_at=now(),check_state=state,check_code=code))
            if not changed.rowcount:
                raise StorageError('revision_conflict')
            self.service._event(db,actor,'source_probed',source_id=ident,
                                outcome='success' if state=='available' else 'partial',code=code)
        return {'state':state,'code':code,'read_only':True,'content_read_tested':False,
                'message':'Se comprobó el listado de la carpeta; no se escribieron archivos.' if state=='available' else 'Origen no disponible o pendiente de validación.'}
