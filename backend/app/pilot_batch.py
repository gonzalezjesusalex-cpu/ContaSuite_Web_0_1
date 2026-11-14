"""Checkpointed analysis only, on existing reconcile staging. No company/document writes."""

import base64
import json
import os
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from .database import session
from .security import auth, Principal
from .company_import_models import sessions, rows

router = APIRouter(prefix='/api/pilot-batches', tags=['Análisis por lotes'])


def authorize(p, db):
    p.require_admin()
    url = db.get_bind().url
    if p.bootstrap or not p.session_id:
        raise HTTPException(403, 'Sesión personal requerida.')
    if not (
        os.getenv('CS_BATCH_DATABASE', '').startswith('contasuite_pilot_')
        and url.database == os.getenv('CS_BATCH_DATABASE')
        and url.get_backend_name() == 'postgresql'
        and url.host in {'127.0.0.1', 'localhost'}
    ):
        raise HTTPException(423, 'Análisis por lotes deshabilitado fuera de su base exclusiva.')


@router.get('')
def current(p: Principal = Depends(auth), db=Depends(session)):
    authorize(p, db)
    value = (
        db.execute(
            select(sessions)
            .where(sessions.c.source == 'local_batch', sessions.c.owner_id == p.subject)
            .order_by(sessions.c.created_at.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if not value:
        return {'analysis': None}
    imported = db.scalar(
        select(func.count())
        .select_from(rows)
        .where(rows.c.session_id == value['id'], rows.c.proposal['import_document_id'].as_string().is_not(None))
    )
    return {
        'analysis': {
            'imported_documents': imported,
            'id': value['id'],
            'status': value['status'],
            'summary': value['summary'],
            'confirmation_enabled': False,
        }
    }


@router.get('/{ident}/rows')
def page(
    ident: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    state: Literal['all', 'conflicts', 'duplicates', 'errors', 'unknown'] = 'all',
    p: Principal = Depends(auth),
    db=Depends(session),
):
    authorize(p, db)
    owner = db.scalar(
        select(sessions.c.id).where(
            sessions.c.id == ident, sessions.c.source == 'local_batch', sessions.c.owner_id == p.subject
        )
    )
    if not owner:
        raise HTTPException(404, 'Análisis no disponible.')
    criteria = [rows.c.session_id == ident, rows.c.number > 0]
    if state == 'conflicts':
        criteria.append(rows.c.proposal['conflict'].as_boolean() == True)
    elif state == 'duplicates':
        criteria.append(rows.c.proposal['duplicate'].as_boolean() == True)
    elif state == 'errors':
        criteria.append(rows.c.proposal['error'].as_string().is_not(None))
    elif state == 'unknown':
        criteria.append(rows.c.proposal['type'].as_string() == 'unknown')
    total = db.scalar(select(func.count()).select_from(rows).where(*criteria))
    records = db.execute(select(rows).where(*criteria).order_by(rows.c.number).offset(offset).limit(limit))
    return {
        'items': [{'number': r.number, **r.proposal} for r in records],
        'offset': offset,
        'limit': limit,
        'total': total,
    }


class Extractor:
    """One bounded child, recycled every 100 files; wall-clock timeout includes I/O."""

    def __init__(self):
        self.proc = None
        self.used = 0
        self.pool = ThreadPoolExecutor(max_workers=1)

    def stop(self):
        if self.proc:
            if self.proc.poll() is None:
                self.proc.kill()
            self.proc.wait()
            self.proc = None

    def close(self):
        self.stop()
        self.pool.shutdown(wait=True)

    def extract(self, content, name):
        if self.proc is None or self.used >= 100 or self.proc.poll() is not None:
            self.stop()
            self.used = 0
            code = 'import sys,runpy;sys.path.insert(0,sys.argv[1]);runpy.run_module("app.pilot_batch_extract",run_name="__main__")'
            self.proc = subprocess.Popen(
                [sys.executable, '-B', '-c', code, str(Path(__file__).resolve().parents[1])],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        payload = (json.dumps({'name': name, 'content': base64.b64encode(content).decode()}) + '\n').encode()
        proc = self.proc

        def exchange():
            proc.stdin.write(payload)
            proc.stdin.flush()
            result = proc.stdout.readline(65537)
            if len(result) > 65536:
                raise ValueError
            return json.loads(result)

        try:
            result = self.pool.submit(exchange).result(timeout=10)
            self.used += 1
            return result
        except Exception:  # noqa: BLE001 - extractor failure is recorded as type unknown and the worker is restarted
            self.stop()
            return {
                'type': 'unknown',
                'period': None,
                'identities': [],
                'evidence': {'readable': False, 'complete': False, 'reason': 'extraction_timeout_or_error', 'rfcs': []},
            }


def finalize(db, ident):
    hashes = Counter()
    uuids = {}
    counts = Counter()
    types = Counter()
    candidates = {}
    query = (
        select(rows.c.number, rows.c.proposal)
        .where(rows.c.session_id == ident, rows.c.number > 0)
        .order_by(rows.c.number)
    )
    for number, r in db.execute(query.execution_options(yield_per=100)):
        if r.get('sha256'):
            hashes[r['sha256']] += 1
        u = r.get('result', {}).get('evidence', {}).get('cfdi_uuid')
        if u:
            uuids.setdefault(u, set()).add(r['sha256'])
        types[r.get('type', 'unknown')] += 1
        counts['errors' if r.get('error') else 'classified' if r.get('type') != 'unknown' else 'unclassified'] += 1
        for c in r.get('result', {}).get('identities', []):
            key = c['rfc']
            old = candidates.setdefault(
                key, {'rfc': key, 'name': c.get('name', ''), 'occurrences': 0, 'source': 'Contenido XML declarado'}
            )
            old['occurrences'] += 1
    from sqlalchemy import update

    for number, r in db.execute(query.execution_options(yield_per=100)):
        u = r.get('result', {}).get('evidence', {}).get('cfdi_uuid')
        conflict = (
            bool(u and len(uuids[u]) > 1)
            or r.get('result', {}).get('evidence', {}).get('uuid_status') == 'contradictory'
        )
        duplicate = bool(r.get('sha256') and hashes[r['sha256']] > 1)
        if conflict:
            counts['conflicts'] += 1
        if duplicate:
            counts['duplicates'] += 1
        if conflict or duplicate:
            db.execute(
                update(rows)
                .where(rows.c.session_id == ident, rows.c.number == number)
                .values(proposal={**r, 'conflict': conflict, 'duplicate': duplicate})
            )
    return {
        'counts': dict(counts),
        'types': dict(types),
        'identity_candidates': sorted(candidates.values(), key=lambda c: -c['occurrences'])[:100],
        'additional_candidates': max(0, len(candidates) - 100),
        'authority_validated': False,
        'confirmation_enabled': False,
    }
