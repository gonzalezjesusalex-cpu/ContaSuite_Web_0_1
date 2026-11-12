"""Persistent local indexing queue. One leased worker globally; source bytes are never written.

Checkpoints are bounded by the provider's scan limit. On restart enumeration repeats,
but completed file digests are skipped. Missing files are inferred ONLY after a full,
error-free traversal, never after a limit, unavailable directory or interrupted scan.
"""
import base64
import hashlib
import json
import subprocess
import sys
import threading
from pathlib import Path
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update, or_, func
from ..models import (Company, Document, DocumentVersion, DocumentLocation, StorageIndexJob as Job,
                      DocumentClassificationReview as Review, StorageSource, StorageWorkerState, now)
from .providers import ScanIssue, StorageError
from .service import StorageActor
from .classifier import catalog_digest

LEASE_SECONDS = 120
WORKER_ACTOR = StorageActor('cs_storage_indexer', admin=True)
CLASSIFY_SLOT = threading.BoundedSemaphore(1)


def check_lease(db, job_id, owner):
    # This UPDATE also serializes completion with competing claims on both DB dialects.
    changed = db.execute(update(Job).where(Job.id == job_id, Job.status == 'running',
        Job.lease_owner == owner, Job.lease_until > now()).values(lease_until=now() + timedelta(seconds=LEASE_SECONDS)))
    if not changed.rowcount:
        raise StorageError('lease_lost')
    return db.get(Job, job_id)


def public_job(job):
    return dict(id=job.id, source_id=job.source_id, status=job.status, counters=job.counters,
                error_code=job.error_code, created_at=job.created_at, started_at=job.started_at,
                completed_at=job.completed_at)


class LocalIndexer:
    def __init__(self, service):
        self.service = service

    def tick(self,owner):
        """Heartbeat and due schedules share the global DB mutex; never starts an HTTP worker."""
        with self.service.sessions.begin() as db:
            db.execute(update(StorageSource).where(StorageSource.id=='cs_internal').values(label=StorageSource.label))
            heartbeat=db.get(StorageWorkerState,'indexer')
            if heartbeat is None:
                db.add(StorageWorkerState(id='indexer',owner=owner,heartbeat_at=now()))
            else:
                heartbeat.owner,heartbeat.heartbeat_at=owner,now()
            sources=db.scalars(select(StorageSource).where(StorageSource.kind.in_(['local_folder','windows_smb']),StorageSource.enabled==True,
                StorageSource.interval_minutes>0,or_(StorageSource.next_scan_at.is_(None),StorageSource.next_scan_at<=now())))
            count=0
            for source in sources:
                active=db.scalar(select(Job.id).where(Job.source_id==source.id,Job.status.in_(['queued','running'])))
                if not active:
                    db.add(Job(id=str(uuid4()),source_id=source.id,status='queued',requested_by=WORKER_ACTOR.subject,
                               checkpoint={'seen':{},'issues':[]},counters={}))
                    self.service._event(db,WORKER_ACTOR,'index_scheduled',source_id=source.id)
                    count+=1
                source.next_scan_at=now()+timedelta(minutes=source.interval_minutes)
            return count

    def _authorize(self, actor):
        actor.require('index')
        if not actor.admin:
            raise StorageError('forbidden')

    def enqueue(self, actor, source_id):
        self._authorize(actor)
        with self.service.sessions.begin() as db:
            source = db.get(StorageSource, source_id)
            if not source or source.kind not in {'local_folder','windows_smb'} or not source.enabled:
                raise StorageError('source_not_found')
            db.execute(update(StorageSource).where(StorageSource.id == source_id).values(label=source.label))
            active = db.scalar(select(Job).where(Job.source_id == source_id, Job.status.in_(['queued', 'running'])))
            if active:
                return public_job(active)
            # Validate roots without changing the source or accepting a client path.
            self.service._provider(source)
            job = Job(id=str(uuid4()), source_id=source_id, requested_by=actor.subject,
                      status='queued', checkpoint={'seen': {}, 'issues': []}, counters={})
            db.add(job)
            self.service._event(db, actor, 'index_queued', source_id=source_id)
            db.flush()
            return public_job(job)

    def jobs(self, actor):
        self._authorize(actor)
        with self.service.sessions() as db:
            return [public_job(j) for j in db.scalars(select(Job).order_by(Job.created_at.desc()).limit(30))]

    def claim(self, owner):
        with self.service.sessions.begin() as db:
            # Existing repository row is a DB-backed global claim mutex (no filesystem lock).
            db.execute(update(StorageSource).where(StorageSource.id == 'cs_internal').values(label=StorageSource.label))
            if db.scalar(select(Job.id).where(Job.status == 'running', Job.lease_until > now())):
                return None
            job = db.scalar(select(Job).where(or_(Job.status == 'queued',
                (Job.status == 'running') & (Job.lease_until <= now()))).order_by(Job.created_at, Job.id).limit(1))
            if job is None:
                return None
            job.status, job.lease_owner = 'running', owner
            job.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
            job.started_at = job.started_at or now()
            db.flush()
            return job.id

    def _classification(self, doc, companies, actor=WORKER_ACTOR):
        if not CLASSIFY_SLOT.acquire(blocking=False):
            raise StorageError('classifier_busy')
        try:
            return self._extract(doc, companies, actor)
        finally:
            CLASSIFY_SLOT.release()

    def _extract(self, doc, companies, actor):
        if doc.size > 25 * 1024 * 1024 or len(companies) > 10000:
            return {'evidence': {'rule': 'rfc-v1', 'reason': 'extraction_limit', 'rfcs': [], 'complete': False},
                    'links': [], 'automatic': False, 'type': 'unknown', 'period': None}
        with self.service.read(actor, doc.id) as content:
            payload = json.dumps({'name': content.filename, 'companies': companies,
                                 'content': base64.b64encode(content.stream.read()).decode('ascii')}).encode()
        try:
            completed = subprocess.run([sys.executable, '-m', 'app.storage.classify_process'], input=payload,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=25, check=True,
                cwd=Path(__file__).resolve().parents[2])
            if len(completed.stdout) > 65536:
                raise ValueError('large_result')
            return json.loads(completed.stdout)
        except (subprocess.SubprocessError, ValueError, OSError):
            return {'evidence': {'rule': 'rfc-v1', 'reason': 'extraction_limit', 'rfcs': [], 'complete': False},
                    'links': [], 'automatic': False, 'type': 'unknown', 'period': None}

    def run(self, job_id, owner, *, stop_after=None):
        """Run claimed job; stop_after is a graceful checkpoint boundary for CLI/tests."""
        service = self.service
        with service.sessions.begin() as db:
            job = check_lease(db, job_id, owner)
            source_id = job.source_id
            source = db.get(StorageSource, source_id)
            try:
                provider = service._provider(source)
                availability = provider.availability()
                if availability.state != 'available':
                    raise StorageError(availability.code or 'root_unavailable')
            except StorageError as exc:
                job.status, job.error_code, job.completed_at = 'failed', exc.code, now()
                job.lease_until, job.lease_owner = None, None
                service._event(db, WORKER_ACTOR, 'index_failed', source_id=source_id, outcome='error', code=exc.code)
                return
            checkpoint, counters = dict(job.checkpoint), dict(job.counters)
            companies = [dict(id=c.id, rfc=c.rfc) for c in db.scalars(select(Company))]
        seen = dict(checkpoint.get('seen', {}))
        issues = list(checkpoint.get('issues', []))
        processed = 0
        for entry in provider.enumerate():
            key_hash = hashlib.sha256(entry.key.casefold().encode()).hexdigest()
            if key_hash in seen:
                continue
            if len(seen) >= service.settings.max_scan_entries:
                counters['errors'] = counters.get('errors', 0) + 1
                issues.append({'code': 'scan_limit'})
                break
            outcome, code = 'errors', None
            with service.sessions.begin() as db:
                check_lease(db, job_id, owner)
            if isinstance(entry, ScanIssue):
                code = entry.code
            else:
                try:
                    with service.sessions() as db:
                        old = db.scalar(select(DocumentVersion).join(DocumentLocation,
                            DocumentLocation.version_id == DocumentVersion.id).where(
                            DocumentLocation.source_id == source_id, DocumentLocation.key_digest == key_hash)
                            .order_by(DocumentVersion.number.desc()))
                        previous = old.number if old else 0
                    doc = service.observe_external(WORKER_ACTOR, source_id, entry.key, lease=(job_id, owner))
                    outcome = 'new' if not previous else 'modified' if doc.revision != previous else 'unchanged'
                    with service.sessions() as db:
                        reviewed = db.scalar(select(Review).join(DocumentVersion, Review.version_id == DocumentVersion.id)
                            .where(Review.document_id == doc.id, DocumentVersion.number == doc.revision)
                            .order_by(Review.created_at.desc()).limit(1))
                        already_classified = reviewed is not None and (
                            (reviewed.status == 'resolved' and reviewed.resolution != 'automatic') or
                            reviewed.evidence.get('catalog_digest') == catalog_digest(companies))
                    if outcome != 'unchanged' or not already_classified:
                        result = self._classification(doc, companies)
                        service.apply_classification(WORKER_ACTOR, doc.id, doc.revision, result, lease=(job_id, owner))
                    with service.sessions() as db:
                        version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id,
                                                                 DocumentVersion.number == doc.revision))
                        duplicate = db.scalar(select(func.count()).select_from(DocumentVersion).join(Document,
                            Document.id == DocumentVersion.document_id).where(DocumentVersion.number == Document.storage_revision,
                            DocumentVersion.sha256 == version.sha256, DocumentVersion.document_id != doc.id))
                    if duplicate:
                        counters['duplicates'] = counters.get('duplicates', 0) + 1
                except StorageError as exc:
                    if exc.code == 'lease_lost':
                        raise
                    code = exc.code
            if code:
                if len(issues) < 100:
                    issues.append({'key_digest': key_hash, 'code': code})
            seen[key_hash] = outcome
            counters[outcome] = counters.get(outcome, 0) + 1
            with service.sessions.begin() as db:
                job = check_lease(db, job_id, owner)
                job.checkpoint = {'seen': seen, 'issues': issues}
                job.counters = dict(counters)
                if code:
                    if entry.key and code not in {'scan_limit'}:
                        state = {'access_denied': 'denied', 'missing': 'missing',
                                 'file_changed': 'changed'}.get(code, 'unavailable')
                        db.execute(update(DocumentLocation).where(DocumentLocation.source_id == source_id,
                            DocumentLocation.availability != 'superseded', or_(DocumentLocation.relative_key == entry.key,
                            DocumentLocation.relative_key.startswith(entry.key + '/', autoescape=True)))
                            .values(availability=state, error_code=code))
                    service._event(db, WORKER_ACTOR, 'index_entry_failed', source_id=source_id, outcome='error', code=code)
            processed += 1
            if stop_after and processed >= stop_after:
                with service.sessions.begin() as db:
                    job = check_lease(db, job_id, owner)
                    job.status, job.lease_until, job.lease_owner = 'queued', None, None
                return
        with service.sessions.begin() as db:
            job = check_lease(db, job_id, owner)
            if not counters.get('errors'):
                locations = db.scalars(select(DocumentLocation).where(DocumentLocation.source_id == source_id,
                    DocumentLocation.availability != 'superseded'))
                for location in locations:
                    if location.key_digest not in seen and not provider._excluded(location.relative_key):
                        location.availability, location.error_code = 'missing', 'missing'
                        counters['missing'] = counters.get('missing', 0) + 1
            job.status = 'completed_with_errors' if counters.get('errors') else 'completed'
            job.error_code = issues[0]['code'] if issues else None
            job.counters, job.completed_at = dict(counters), now()
            job.lease_owner, job.lease_until = None, None
            service._event(db, WORKER_ACTOR, 'index_completed', source_id=source_id,
                           outcome='partial' if issues else 'success', code=job.error_code)
