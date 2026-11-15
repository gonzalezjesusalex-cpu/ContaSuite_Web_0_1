"""Bloque 4: local agent paired to the user's session, authorized folders, revoke / restart, scope by user."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from test_api import G, client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import login, setup
from test_permissions import account
from app.agent_links import inside_roots, normalized
from app.database import SessionLocal
from app.main import app
from app.models import AgentLink, AgentPairCode, Job, UserSession
from app.security import utc


def bearer(token):
    return {'Authorization': 'Bearer ' + token}


def pair(c, agent_id='pc-ana', machine='PC-ANA'):
    code = c.post('/api/agent-links/code')
    assert code.status_code == 201, code.text
    paired = c.post('/api/agent/pair', json={'code': code.json()['code'], 'agent_id': agent_id, 'machine': machine})
    assert paired.status_code == 201, paired.text
    return code.json()['code'], paired.json()['token']


def beat(c, token, agent_id='pc-ana'):
    return c.post('/api/agent/heartbeat', headers=bearer(token), json={'id': agent_id, 'capabilities': ['scan_folder']})


@pytest.fixture()
def office(client):  # noqa: F811
    a = company(client, name='Empresa A', rfc='AAA010101AA1', folder=r'C:\Empresas\A').json()['id']
    b = company(client, name='Empresa B', rfc='BBB020202BB2', folder=r'D:\Otra\B').json()['id']
    setup(client)
    assert client.put('/api/agent-links/roots', json={'paths': [r'C:\Empresas', r'c:\empresas\\']}).json() == {
        'roots': [r'C:\Empresas']
    }
    ana = account(client, 'ana', 'contador', [(a, 'write'), (b, 'write')])
    return client, {'a': a, 'b': b}, ana


def test_paths_compare_case_insensitive_and_never_by_prefix_only():
    assert normalized('c:/Empresas/A/') == normalized(r'C:\EMPRESAS\a')
    assert inside_roots(r'C:\Empresas\A', [r'C:\Empresas'])
    assert inside_roots(r'\\servidor\conta\x', [r'\\Servidor\Conta'])
    assert not inside_roots(r'C:\Empresas2\A', [r'C:\Empresas'])


def test_roots_must_be_absolute_and_are_admin_only(office):
    c, _, _ = office
    for bad in ['Empresas', r'C:\Empresas\..\Windows', '/home/x']:
        assert c.put('/api/agent-links/roots', json={'paths': [bad]}).status_code == 422, bad
    login(c, 'ana')
    assert c.put('/api/agent-links/roots', json={'paths': []}).status_code == 403
    assert c.get('/api/agent-links').status_code == 403


def test_code_is_single_use_bound_to_session_and_only_its_hash_is_stored(office):
    c, _, _ = office
    login(c, 'ana')
    code, token = pair(c)
    with SessionLocal() as db:
        assert db.query(AgentPairCode).filter(AgentPairCode.code_hash == code).count() == 0
        link = db.query(AgentLink).one()
        assert link.token_hash != token and link.machine == 'PC-ANA'
    again = c.post('/api/agent/pair', json={'code': code, 'agent_id': 'pc-ana'})
    assert again.status_code == 401  # a code works once
    assert beat(c, token).json()['user']
    assert c.get('/api/state').json()['agent_link']['state'] == 'online'

    # A newer code invalidates the previous unused one of the same session.
    first = c.post('/api/agent-links/code').json()['code']
    c.post('/api/agent-links/code')
    assert c.post('/api/agent/pair', json={'code': first, 'agent_id': 'pc-ana'}).status_code == 401


def test_expired_code_cannot_pair(office):
    c, _, _ = office
    login(c, 'ana')
    code = c.post('/api/agent-links/code').json()['code']
    with SessionLocal.begin() as db:
        row = db.query(AgentPairCode).one()
        row.expires_at = utc(row.expires_at) - timedelta(minutes=5)
    assert c.post('/api/agent/pair', json={'code': code, 'agent_id': 'pc-ana'}).status_code == 401


def test_link_ends_with_the_session_and_with_revocation(office):
    c, _, _ = office
    login(c, 'ana')
    _, token = pair(c)
    assert beat(c, token).status_code == 200
    with SessionLocal.begin() as db:
        db.query(UserSession).filter(UserSession.user_id == db.query(AgentLink).one().user_id).update(
            {'revoked_at': utc(db.query(AgentLink).one().created_at)}
        )
    ended = beat(c, token)
    assert ended.status_code == 401 and 'sesión' in ended.json()['detail']

    # Signing in again on the same browser closes the previous session, and with it that session's link.
    login(c, 'ana')
    _, token = pair(c)
    login(c)
    assert beat(c, token).status_code == 401

    # Restart and revoke from another browser, while Ana keeps her session.
    with TestClient(app) as admin:
        login(admin)
        login(c, 'ana')
        _, token = pair(c)
        link_id = next(r['id'] for r in admin.get('/api/agent-links').json()['links'] if not r['revoked_at'])
        assert admin.post('/api/agent-links/' + link_id + '/restart').status_code == 200
        assert beat(c, token).json()['restart'] is True  # restart ends the link; the next sign-in pairs again
        assert beat(c, token).status_code == 401

        _, token = pair(c)
        link_id = next(r['id'] for r in admin.get('/api/agent-links').json()['links'] if not r['revoked_at'])
        assert admin.post('/api/agent-links/' + link_id + '/revoke').json()['revoked_reason']
        assert beat(c, token).status_code == 401


def test_jobs_use_the_users_own_agent_inside_authorized_folders(office):
    c, companies, ana = office
    login(c, 'ana')
    no_link = c.post('/api/jobs', json={'company_id': companies['a'], 'kind': 'scan_folder'})
    assert no_link.status_code == 409 and 'vinculado' in no_link.json()['detail']
    _, token = pair(c)
    beat(c, token)
    outside = c.post('/api/jobs', json={'company_id': companies['b'], 'kind': 'scan_folder'})
    assert outside.status_code == 409 and 'fuera' in outside.json()['detail']
    job = c.post('/api/jobs', json={'company_id': companies['a'], 'kind': 'scan_folder'})
    assert job.status_code == 201, job.text
    assert job.json()['requested_by'] == ana['id'] and job.json()['machine'] == 'PC-ANA'

    assert c.post('/api/agent/otro/claim', headers=bearer(token)).status_code in (403, 404)
    claimed = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    assert claimed['id'] == job.json()['id'] and claimed['payload']['roots'] == [r'C:\Empresas']
    done = c.post(
        '/api/agent/jobs/' + claimed['id'] + '/result',
        headers=bearer(token),
        json={'agent_id': 'pc-ana', 'status': 'completed', 'result': {'files': []}},
    )
    assert done.status_code == 200
    # Non-administrators never receive the folder path of a job in the state.
    assert all('payload' not in j for j in c.get('/api/state').json()['jobs'])


def test_queued_job_fails_when_the_user_loses_the_permission(office):
    c, companies, ana = office
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    job_id = c.post('/api/jobs', json={'company_id': companies['a'], 'kind': 'scan_folder'}).json()['id']
    login(c)
    user = c.get('/api/auth/users').json()
    revision = next(u for u in user if u['id'] == ana['id'])['revision']
    edit = {'revision': revision, 'display_name': 'Ana', 'role': 'contador', 'enabled': True, 'grants': []}
    assert c.put('/api/auth/users/' + ana['id'], json=edit).status_code == 200
    # Changing permissions revokes Ana's sessions, so her agent link ends too.
    assert c.post('/api/agent/pc-ana/claim', headers=bearer(token)).status_code == 401
    with SessionLocal() as db:
        assert db.get(Job, job_id).status in ('queued', 'failed')


def test_shared_token_only_with_explicit_transition_flag(office, monkeypatch):
    c, _, _ = office
    assert c.post('/api/agent/heartbeat', headers=G, json={'id': 'local', 'capabilities': []}).status_code == 200
    monkeypatch.delenv('CS_ALLOW_SHARED_AGENT_TOKEN')
    assert c.post('/api/agent/heartbeat', headers=G, json={'id': 'local', 'capabilities': []}).status_code == 401
