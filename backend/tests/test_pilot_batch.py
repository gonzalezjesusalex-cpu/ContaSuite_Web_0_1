import hashlib
import pytest
from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select
from test_api import client
from test_storage_core import core
from test_company_import import imported, ADMIN
from test_pilot_import import xml
from app.pilot_batch import Extractor, finalize, authorize
from app.company_import_models import sessions, rows
from app.models import now
from fastapi import HTTPException


def test_recycled_extractor_synthetic_xml_and_bad_content():
    worker = Extractor()
    try:
        for _ in range(3):
            result = worker.extract(xml(), 'test.xml')
            assert result['evidence']['readable'] and result['evidence']['cfdi_uuid']
        assert worker.extract(b'not xml', 'bad.xml')['evidence']['readable'] is False
        worker.used = 100
        assert worker.extract(xml(), 'test.xml')['type'] == 'cfdi'
    finally:
        worker.close()


def test_global_duplicates_and_uuid_conflicts_across_checkpoints(imported):
    _, factory, _ = imported
    ident = str(uuid4())
    stamp = now()
    with factory.begin() as db:
        db.execute(
            sessions.insert().values(
                id=ident,
                owner_id=ADMIN.subject,
                idempotency_key=ident,
                source='local_batch',
                source_sha256='0' * 64,
                summary={},
                created_at=stamp,
                expires_at=stamp + timedelta(days=1),
                status='analysing',
            )
        )
        for n, h, u in [(1, 'a', 'U1'), (101, 'a', 'U1'), (201, 'b', 'U1')]:
            db.execute(
                rows.insert().values(
                    session_id=ident,
                    number=n,
                    revision=0,
                    proposal={'sha256': h, 'type': 'cfdi', 'result': {'evidence': {'cfdi_uuid': u}, 'identities': []}},
                )
            )
    with factory.begin() as db:
        result = finalize(db, ident)
        assert result['counts']['duplicates'] == 2 and result['counts']['conflicts'] == 3
        assert all(r['conflict'] for r in db.scalars(select(rows.c.proposal).where(rows.c.session_id == ident)))
    with factory.begin() as db:
        assert finalize(db, ident)['counts'] == result['counts']


def test_batch_not_available_on_wrong_database(imported, monkeypatch):
    _, factory, _ = imported
    monkeypatch.setenv('CS_BATCH_DATABASE', 'contasuite_pilot_testing')
    with factory() as db:
        with pytest.raises(HTTPException) as e:
            authorize(ADMIN, db)
        assert e.value.status_code == 423


def test_batch_http_pagination_scope_and_no_confirm(imported, monkeypatch):
    c, factory, app = imported
    import app.pilot_batch as batch

    monkeypatch.setattr(batch, 'authorize', lambda p, db: p.require_admin())
    ident = str(uuid4())
    stamp = now()
    with factory.begin() as db:
        db.execute(
            sessions.insert().values(
                id=ident,
                owner_id=ADMIN.subject,
                idempotency_key=ident,
                source='local_batch',
                source_sha256='0' * 64,
                summary={'total': 101, 'processed': 0},
                created_at=stamp,
                expires_at=stamp + timedelta(days=1),
                status='analysing',
            )
        )
        db.execute(
            rows.insert(),
            [
                {
                    'session_id': ident,
                    'number': n,
                    'revision': 0,
                    'proposal': {'key': 'synthetic.xml', 'status': 'queued'},
                }
                for n in range(1, 102)
            ],
        )
    assert c.get('/api/pilot-batches').json()['analysis']['id'] == ident
    result = c.get(f'/api/pilot-batches/{ident}/rows?offset=100&limit=50')
    assert result.status_code == 200 and len(result.json()['items']) == 1
    assert result.headers['cache-control'] == 'no-store, private'
    assert c.get(f'/api/pilot-batches/{ident}/rows?limit=1000').status_code == 422
    assert c.get('/api/pilot-batches/not-owned/rows').status_code == 404
    assert c.post(f'/api/company-imports/{ident}/confirm', json={'confirmed': True}).status_code == 404
    with factory.begin() as db:
        from sqlalchemy import update

        db.execute(
            update(rows)
            .where(rows.c.session_id == ident, rows.c.number == 1)
            .values(
                proposal={
                    'key': 'synthetic.xml',
                    'status': 'analysed',
                    'conflict': True,
                    'duplicate': True,
                    'type': 'unknown',
                    'error': 'synthetic_error',
                }
            )
        )
    for state in ['conflicts', 'duplicates', 'errors', 'unknown']:
        result = c.get(f'/api/pilot-batches/{ident}/rows?state={state}').json()
        assert result['total'] == 1 and result['items'][0]['number'] == 1
    assert c.get(f'/api/pilot-batches/{ident}/rows?state=invalid').status_code == 422
