"""Agent jobs left in `running` expire to `failed`; no schema change (claim time kept in result JSON)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from test_api import client, A, G, TEMP, company  # noqa: F401  Isolated environment before app imports.
from app.agent_jobs import expire_stale_jobs, timeout_minutes
from app.database import SessionLocal
from app.models import Audit, Job


def claimed_job(client):
    c = company(client, folder=str(Path(TEMP.name))).json()
    client.post('/api/agent/heartbeat', headers=G, json={'id': 'local', 'capabilities': ['scan_folder']})
    created = client.post(
        '/api/jobs', headers=A, json={'company_id': c['id'], 'agent_id': 'local', 'kind': 'scan_folder'}
    )
    assert created.status_code == 201
    job = client.post('/api/agent/local/claim', headers=G).json()
    assert job['id'] == created.json()['id'] and job['status'] == 'running'
    return c, job


def backdate(job_id, minutes):
    with SessionLocal.begin() as db:
        job = db.get(Job, job_id)
        claimed = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        job.result = {'claimed_at': claimed.isoformat()}


def status(job_id):
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        return job.status, job.result


def test_claim_records_time_and_recent_job_keeps_running(client):
    _, job = claimed_job(client)
    assert datetime.fromisoformat(job['result']['claimed_at']) <= datetime.now(timezone.utc)
    backdate(job['id'], 14)
    client.get('/api/state', headers=A)
    assert status(job['id'])[0] == 'running'


def test_stale_job_fails_with_message_and_late_result_is_rejected(client):
    c, job = claimed_job(client)
    backdate(job['id'], 16)
    state = client.get('/api/state', headers=A).json()
    shown = next(j for j in state['jobs'] if j['id'] == job['id'])
    assert shown['status'] == 'failed' and 'no entregó resultado en 15 minutos' in shown['result']['error']
    late = client.post(
        '/api/agent/jobs/' + job['id'] + '/result',
        headers=G,
        json={'agent_id': 'local', 'status': 'completed', 'result': {'files': []}},
    )
    assert late.status_code == 409
    assert status(job['id'])[0] == 'failed'
    assert client.post('/api/agent/local/claim', headers=G).json() is None  # never re-queued
    with SessionLocal() as db:
        assert db.scalar(select(Audit).where(Audit.company_id == c['id'], Audit.action.like('%caducado%')))


def test_claim_and_create_also_expire_stale_jobs(client):
    c, job = claimed_job(client)
    backdate(job['id'], 30)
    assert client.post('/api/agent/local/claim', headers=G).json() is None
    assert status(job['id'])[0] == 'failed'
    queued = client.post(
        '/api/jobs', headers=A, json={'company_id': c['id'], 'agent_id': 'local', 'kind': 'scan_folder'}
    )
    second = client.post('/api/agent/local/claim', headers=G).json()
    assert second['id'] == queued.json()['id']
    backdate(second['id'], 30)
    created = client.post(
        '/api/jobs', headers=A, json={'company_id': c['id'], 'agent_id': 'local', 'kind': 'scan_folder'}
    )
    assert created.status_code == 201 and status(second['id'])[0] == 'failed'


def test_legacy_running_job_without_marker_uses_creation_time(client):
    _, job = claimed_job(client)
    with SessionLocal.begin() as db:
        row = db.get(Job, job['id'])
        row.result = {}
        row.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    with SessionLocal() as db:
        assert expire_stale_jobs(db) == [job['id']]
    assert status(job['id'])[0] == 'failed'


def test_completed_result_within_timeout_is_kept(client):
    _, job = claimed_job(client)
    done = client.post(
        '/api/agent/jobs/' + job['id'] + '/result',
        headers=G,
        json={'agent_id': 'local', 'status': 'completed', 'result': {'files': []}},
    )
    assert done.status_code == 200
    with SessionLocal() as db:
        assert expire_stale_jobs(db, current=datetime.now(timezone.utc) + timedelta(days=1)) == []
    assert status(job['id']) == ('completed', {'files': []})


def test_timeout_configuration(monkeypatch):
    assert timeout_minutes('15') == 15 and timeout_minutes(5) == 5
    for invalid in ('4', '0', '-1', 'x'):
        with pytest.raises(ValueError):
            timeout_minutes(invalid)
    monkeypatch.delenv('CS_AGENT_JOB_TIMEOUT_MINUTES', raising=False)
    assert timeout_minutes() == 15
