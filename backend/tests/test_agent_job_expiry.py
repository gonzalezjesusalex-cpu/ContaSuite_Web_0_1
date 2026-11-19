"""Agent jobs left in `running` expire to `failed`; no schema change (claim time kept in result JSON)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from test_api import client, A, G, TEMP, company  # noqa: F401  Isolated environment before app imports.
from test_agent_links import beat, bearer, office, pair  # noqa: F401
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


def beat_with(client, job_id, agent_id='local'):
    return client.post(
        '/api/agent/heartbeat', headers=G, json={'id': agent_id, 'capabilities': ['scan_folder'], 'job_id': job_id}
    )


def expire_now():
    with SessionLocal() as db:
        return expire_stale_jobs(db)


def test_heartbeat_with_job_id_keeps_a_long_job_alive_and_keeps_other_keys(client):
    _, job = claimed_job(client)
    backdate(job['id'], 20)
    with SessionLocal.begin() as db:
        row = db.get(Job, job['id'])
        row.result = {**row.result, 'progreso': {'hechas': 3}, 'cancelar': True}
    assert beat_with(client, job['id']).status_code == 200
    assert expire_now() == []
    state, result = status(job['id'])
    assert state == 'running' and result['progreso'] == {'hechas': 3} and result['cancelar'] is True
    assert datetime.now(timezone.utc) - datetime.fromisoformat(result['claimed_at']) < timedelta(minutes=1)


def test_old_heartbeat_without_job_id_does_not_renew_and_job_expires(client):
    _, job = claimed_job(client)
    backdate(job['id'], 20)
    ok = client.post('/api/agent/heartbeat', headers=G, json={'id': 'local', 'capabilities': ['scan_folder']})
    assert ok.status_code == 200
    assert expire_now() == [job['id']] and status(job['id'])[0] == 'failed'


def test_heartbeat_of_another_agent_does_not_renew(client):
    _, job = claimed_job(client)
    backdate(job['id'], 20)
    assert beat_with(client, job['id'], agent_id='otro').status_code == 200
    assert expire_now() == [job['id']]


def test_heartbeat_does_not_revive_a_finished_job(client):
    _, job = claimed_job(client)
    backdate(job['id'], 20)
    assert expire_now() == [job['id']]
    assert beat_with(client, job['id']).status_code == 200
    assert status(job['id'])[0] == 'failed'


def test_linked_heartbeat_only_renews_the_users_own_job(office):  # noqa: F811
    from test_accounts import login

    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    created = c.post('/api/jobs', json={'company_id': companies['a'], 'kind': 'scan_folder'})
    assert created.status_code == 201, created.text
    job = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    assert job['id'] == created.json()['id']

    def renew():
        backdate(job['id'], 20)
        body = {'id': 'pc-ana', 'capabilities': ['scan_folder'], 'job_id': job['id']}
        assert c.post('/api/agent/heartbeat', headers=bearer(token), json=body).status_code == 200
        return datetime.now(timezone.utc) - datetime.fromisoformat(status(job['id'])[1]['claimed_at'])

    assert renew() < timedelta(minutes=1)  # the user's own job is renewed
    with SessionLocal.begin() as db:
        db.get(Job, job['id']).requested_by = 'otra-persona'
    assert renew() > timedelta(minutes=19)  # a job of another user is not


def test_closing_interrupts_running_jobs_as_failed_with_the_message(client):
    from app.agent_jobs import INTERRUPTED, interrupt_running_jobs, running_jobs

    c, job = claimed_job(client)
    with SessionLocal() as db:
        assert running_jobs(db) == [{'id': job['id'], 'kind': 'scan_folder', 'company_id': c['id']}]
        assert interrupt_running_jobs(db, ['otro-id']) == []  # only the jobs asked for
    assert status(job['id'])[0] == 'running'
    with SessionLocal() as db:
        assert interrupt_running_jobs(db, [job['id']]) == [job['id']]
        assert running_jobs(db) == []
    state, result = status(job['id'])
    assert state == 'failed' and result['error'] == INTERRUPTED == 'Interrumpido al cerrar ContaSuite'
    assert 'claimed_at' in result and 'interrupted_at' in result
    with SessionLocal() as db:
        assert db.scalar(select(Audit).where(Audit.company_id == c['id'], Audit.action.like('%interrumpido%')))
    # A late result from the agent is refused, and a finished job is never touched again.
    late = client.post(
        '/api/agent/jobs/' + job['id'] + '/result',
        headers=G,
        json={'agent_id': 'local', 'status': 'completed', 'result': {'files': []}},
    )
    assert late.status_code == 409
    with SessionLocal() as db:
        assert interrupt_running_jobs(db) == []
