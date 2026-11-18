"""Persistent virtual index of each company's folder (cs_0014).

The local agent sends, in batches, one row per file it found (original path, size, SHA-256, group and virtual path).
This module stores them and compares every scan with the previous state:

- added: a path never seen before;
- changed: same path, different content (SHA-256, or size when a hash could not be read);
- moved: a new path whose SHA-256 equals that of exactly one file that disappeared (the history follows the file);
- restored: a file that had gone missing and is back;
- missing: a file that was in the previous index and is not in this complete scan. It stays listed, never deleted.

A scan whose walk hit its limit never marks anything as missing or moved. Nothing here reads or changes a document.
"""

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .database import session
from .models import Document, DocumentCompanyLink, DocumentVersion, VirtualFile, VirtualScan, now
from .security import Principal, auth

router = APIRouter(prefix='/api/companies/{company_id}/virtual-index', tags=['Índice virtual'])
CHANGES = ('added', 'changed', 'moved', 'restored')


def _changed(stored, row):
    """Different content: by SHA-256 when both sides have one, by size when a hash could not be read."""
    if row.h and stored.sha256:
        return row.h != stored.sha256
    return stored.size != row.s


def ingest_batch(db, job, data):
    """Store one batch of a scan. The scan is created by its first batch and closed by the batch marked `last`."""
    stamp = now()
    scan = db.scalar(select(VirtualScan).where(VirtualScan.job_id == job.id))
    if scan is None:
        scan = VirtualScan(company_id=job.company_id, job_id=job.id, requested_by=job.requested_by, created_at=stamp)
        db.add(scan)
        db.flush()
    if scan.finished_at is not None:
        raise HTTPException(409, 'Este análisis ya se cerró.')
    rows = {r.p: r for r in data.rows}  # a repeated path inside one batch: the last one wins
    existing = {}
    if rows:
        existing = {
            f.path: f
            for f in db.scalars(
                select(VirtualFile).where(VirtualFile.company_id == job.company_id, VirtualFile.path.in_(list(rows)))
            )
        }
    for path, row in rows.items():
        stored = existing.get(path)
        if stored is None:
            db.add(
                VirtualFile(
                    company_id=job.company_id,
                    path=path,
                    name=path.rsplit('/', 1)[-1][:255],
                    size=row.s,
                    mtime_ns=row.m,
                    sha256=row.h,
                    group_key=row.g,
                    section=row.sec,
                    virtual_path=row.v,
                    state=row.st,
                    first_seen=stamp,
                    last_seen=stamp,
                    scan_id=scan.id,
                    last_change='added',
                    last_change_scan=scan.id,
                )
            )
            scan.added += 1
            scan.total += 1
            continue
        if stored.scan_id == scan.id:
            continue  # a batch sent twice (retry after a network failure)
        changed = _changed(stored, row)
        if stored.missing_since is not None:
            stored.missing_since = None
            stored.last_change, stored.last_change_scan = 'restored', scan.id
            scan.restored += 1
        elif changed:
            stored.last_change, stored.last_change_scan = 'changed', scan.id
            scan.changed += 1
        stored.size, stored.mtime_ns = row.s, row.m
        stored.sha256 = row.h or (None if changed else stored.sha256)
        stored.group_key, stored.section, stored.virtual_path, stored.state = row.g, row.sec, row.v, row.st
        stored.last_seen, stored.scan_id = stamp, scan.id
        scan.total += 1
    if data.last:
        _finalize(db, scan, data.complete, stamp)
    db.flush()
    return scan


def _finalize(db, scan, complete, stamp):
    scan.complete, scan.finished_at = complete, stamp
    if not complete:
        return  # a partial walk cannot say what disappeared
    stale = db.scalars(
        select(VirtualFile).where(
            VirtualFile.company_id == scan.company_id,
            VirtualFile.scan_id != scan.id,
            VirtualFile.missing_since.is_(None),
        )
    ).all()
    fresh = db.scalars(
        select(VirtualFile).where(
            VirtualFile.company_id == scan.company_id,
            VirtualFile.last_change == 'added',
            VirtualFile.last_change_scan == scan.id,
            VirtualFile.sha256.is_not(None),
        )
    ).all()
    gone = defaultdict(list)
    for stored in stale:
        if stored.sha256:
            gone[stored.sha256].append(stored)
    arrivals = Counter(f.sha256 for f in fresh)
    moved = set()
    for new in fresh:
        candidates = gone.get(new.sha256) or []
        # A move is only claimed when it is unambiguous on both sides: one arrival, one departure.
        if arrivals[new.sha256] != 1 or len(candidates) != 1:
            continue
        old = candidates[0]
        new.moved_from, new.first_seen, new.last_change = old.path, old.first_seen, 'moved'
        scan.added -= 1
        scan.moved += 1
        moved.add(old.id)
        db.delete(old)
    for stored in stale:
        if stored.id not in moved:
            stored.missing_since = stamp
            scan.missing += 1


def describe(scan):
    return {
        'id': scan.id,
        'created_at': scan.created_at,
        'finished_at': scan.finished_at,
        'complete': scan.complete,
        'total': scan.total,
        'added': scan.added,
        'changed': scan.changed,
        'moved': scan.moved,
        'restored': scan.restored,
        'missing': scan.missing,
    }


def _latest(db, company_id):
    return db.scalar(
        select(VirtualScan)
        .where(VirtualScan.company_id == company_id, VirtualScan.finished_at.is_not(None))
        .order_by(VirtualScan.created_at.desc())
        .limit(1)
    )


@router.get('/summary')
def summary(company_id: str, principal: Principal = Depends(auth), db: Session = Depends(session)):
    principal.require('documentos.ver', company_id)
    scans = db.scalars(
        select(VirtualScan).where(VirtualScan.company_id == company_id).order_by(VirtualScan.created_at.desc()).limit(6)
    ).all()
    sections = dict(
        db.execute(
            select(VirtualFile.section, func.count())
            .where(VirtualFile.company_id == company_id, VirtualFile.missing_since.is_(None))
            .group_by(VirtualFile.section)
        ).all()
    )
    missing = db.scalar(
        select(func.count()).where(VirtualFile.company_id == company_id, VirtualFile.missing_since.is_not(None))
    )
    latest = _latest(db, company_id)
    return {
        'scans': [describe(s) for s in scans],
        'latest': describe(latest) if latest else None,
        'sections': sections,
        'total': sum(sections.values()),
        'missing': missing or 0,
    }


@router.get('/files')
def files(
    company_id: str,
    section: str = Query('', max_length=30),
    change: str = Query('', max_length=10),
    missing: bool = False,
    q: str = Query('', max_length=120),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    principal: Principal = Depends(auth),
    db: Session = Depends(session),
):
    principal.require('documentos.ver', company_id)
    if change and change not in CHANGES:
        raise HTTPException(422, 'Cambio desconocido.')
    query = select(VirtualFile).where(VirtualFile.company_id == company_id)
    query = query.where(VirtualFile.missing_since.is_not(None) if missing else VirtualFile.missing_since.is_(None))
    if section:
        query = query.where(VirtualFile.section == section)
    if change:
        latest = _latest(db, company_id)
        if latest is None:
            return {'rows': [], 'total': 0, 'more': False}
        query = query.where(VirtualFile.last_change == change, VirtualFile.last_change_scan == latest.id)
    if q:
        query = query.where(VirtualFile.path.contains(q, autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(VirtualFile.virtual_path, VirtualFile.path).offset(offset).limit(limit + 1)).all()
    return {
        'rows': [
            {
                'id': f.id,
                'path': f.path,
                'name': f.name,
                'size': f.size,
                'section': f.section,
                'virtual_path': f.virtual_path,
                'state': f.state,
                'change': f.last_change,
                'moved_from': f.moved_from,
                'first_seen': f.first_seen,
                'missing_since': f.missing_since,
            }
            for f in rows[:limit]
        ],
        'total': total,
        'more': len(rows) > limit,
    }


def _links(db, company_id, hashes):
    """Registered document versions of this company whose SHA-256 equals a scanned file: {sha256: (id, revision)}.

    The link only says "this file of the folder has the same bytes as that registered version", so its preview can be
    served by the document center. A hash shared by two different documents is ambiguous and is not linked; nothing
    is merged or reclassified here.
    """
    hashes = sorted({h for h in hashes if h})
    if not hashes:
        return {}
    owned = select(DocumentCompanyLink.document_id).where(DocumentCompanyLink.company_id == company_id)
    found = defaultdict(dict)
    for i in range(0, len(hashes), 500):
        rows = db.execute(
            select(DocumentVersion.sha256, DocumentVersion.document_id, DocumentVersion.number)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                DocumentVersion.sha256.in_(hashes[i : i + 500]),
                or_(Document.company_id == company_id, Document.id.in_(owned)),
            )
        ).all()
        for digest, document_id, number in rows:
            found[digest][document_id] = max(number, found[digest].get(document_id, 0))
    return {digest: next(iter(docs.items())) for digest, docs in found.items() if len(docs) == 1}


@router.get('/tree')
def tree(
    company_id: str,
    prefix: str = Query('', max_length=1200),
    q: str = Query('', max_length=120),
    principal: Principal = Depends(auth),
    db: Session = Depends(session),
):
    """One level of the virtual branch: its folders (with how many files each holds) and its files.

    Files carry the registered document they are linked to (same SHA-256), so the document center can preview the
    original without exposing where it lives. With `q`, the level lists every matching file below `prefix` instead.
    """
    principal.require('documentos.ver', company_id)
    prefix = prefix.strip('/')
    base = prefix + '/' if prefix else ''
    query = select(VirtualFile).where(VirtualFile.company_id == company_id, VirtualFile.missing_since.is_(None))
    if base:
        query = query.where(VirtualFile.virtual_path.startswith(base, autoescape=True))
    if q:
        query = query.where(
            or_(VirtualFile.virtual_path.contains(q, autoescape=True), VirtualFile.path.contains(q, autoescape=True))
        )
    rows = db.scalars(query.order_by(VirtualFile.virtual_path, VirtualFile.path)).all()
    folders, here = Counter(), []
    for f in rows:
        rest = f.virtual_path[len(base) :].strip('/')
        if not q and '/' in rest:
            folders[rest.split('/', 1)[0]] += 1
        else:
            here.append(f)
    limit = 500
    links = _links(db, company_id, [f.sha256 for f in here[:limit]])
    return {
        'prefix': prefix,
        'folders': [{'name': name, 'path': base + name, 'files': n} for name, n in sorted(folders.items())],
        'files': [
            {
                'id': f.id,
                'name': f.virtual_path.rsplit('/', 1)[-1] or f.name,
                'path': f.path,
                'virtual_path': f.virtual_path,
                'size': f.size,
                'section': f.section,
                'state': f.state,
                'change': f.last_change,
                'document_id': links.get(f.sha256, (None, None))[0] if f.sha256 else None,
                'revision': links.get(f.sha256, (None, None))[1] if f.sha256 else None,
            }
            for f in here[:limit]
        ],
        'more': len(here) > limit,
        'total': len(rows),
    }
