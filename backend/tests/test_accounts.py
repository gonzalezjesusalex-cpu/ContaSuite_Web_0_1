from datetime import timedelta
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from test_api import client, A, G, company
from app.main import app
from app.database import SessionLocal, DATA
from app.models import (UserAccount, UserSession, UserCompanyGrant, SecurityEvent, StorageEvent,
                        LoginThrottle, IdentityState, Document, now)
from app.security import digest, SESSION_COOKIE, CSRF_COOKIE
from app.accounts import password_matches

PASSWORD = 'Synthetic-password-42!'
NEW_PASSWORD = 'New-synthetic-password-73!'
XML = b'<Comprobante Fecha="2026-10-01"/>'


def login(c, username='admin', password=PASSWORD):
    result = c.post('/api/auth/login', json={'username':username,'password':password})
    assert result.status_code == 200, result.text
    c.headers['X-CSRF-Token'] = c.cookies.get(CSRF_COOKIE)
    return result


def setup(c):
    result = c.post('/api/auth/bootstrap', headers=A,
        json={'username':'admin','display_name':'Administración de prueba','password':PASSWORD})
    assert result.status_code == 201, result.text
    login(c)
    return result.json()['id']


def add_user(c, username='reader', grants=(), admin=False):
    result = c.post('/api/auth/users', json={'username':username,'display_name':username,'password':PASSWORD,'admin':admin})
    assert result.status_code == 201, result.text
    user = result.json()
    if grants:
        result = c.put('/api/auth/users/'+user['id'], json={'revision':user['revision'], 'display_name':username,
            'admin':admin,'enabled':True,'grants':[{'company_id':cid,'access':access} for cid,access in grants]})
        assert result.status_code == 200, result.text
        user = result.json()
    return user


def upload(c, cid=None, name='file.xml', headers=None):
    return c.post('/api/storage/documents', headers=headers,
        files={'file':(name, XML, 'application/xml')}, data={'company_id':cid or ''})


def test_bootstrap_is_atomic_and_old_key_cannot_bypass_named_identity(client):
    assert client.get('/api/auth/status').json() == {'initialized':False}
    assert client.post('/api/auth/bootstrap', json={'username':'admin','password':PASSWORD,'display_name':'Test'}).status_code == 401
    ident = setup(client)
    assert client.get('/api/auth/status').json() == {'initialized':True}
    assert client.get('/api/auth/me').json()['id'] == ident
    assert client.post('/api/auth/bootstrap', headers=A, json={'username':'other','password':PASSWORD,'display_name':'Other'}).status_code == 409
    client.cookies.clear()
    assert client.get('/api/state', headers=A).status_code == 401
    assert client.get('/api/storage/options', headers=A).status_code == 401
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(UserAccount)) == 1
        assert db.get(IdentityState, 'identity').initialized


def test_passwords_and_sessions_are_hashed_cookie_flags_and_rotation(client):
    ident = setup(client)
    first = client.cookies.get(SESSION_COOKIE)
    response = login(client)
    second = client.cookies.get(SESSION_COOKIE)
    assert first != second
    cookie_header = response.headers.get_list('set-cookie')
    assert any('HttpOnly' in value and 'SameSite=strict' in value and 'Path=/api' in value for value in cookie_header)
    with SessionLocal() as db:
        user = db.get(UserAccount, ident)
        assert user.password_hash.startswith('scrypt-v1$') and PASSWORD not in user.password_hash
        assert password_matches(PASSWORD, user.password_hash)
        assert db.get(UserSession, digest(first)).revoked_at
        session = db.get(UserSession, digest(second))
        assert session.csrf_hash == digest(client.cookies.get(CSRF_COOKIE))
        assert second not in str(session.__dict__)
    assert client.get('/api/auth/me', headers=A).json()['id'] == ident
    assert response.headers['Cache-Control'] == 'private, no-store'


def test_csrf_and_origin_checks(client):
    setup(client)
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.post('/api/auth/logout').status_code == 403
    assert client.post('/api/auth/logout', headers={'X-CSRF-Token':'wrong'}).status_code == 403
    assert client.post('/api/auth/logout', headers={'X-CSRF-Token':csrf,'Origin':'https://evil.invalid'}).status_code == 403
    assert client.post('/api/auth/logout', headers={'X-CSRF-Token':csrf,'Sec-Fetch-Site':'cross-site'}).status_code == 403
    assert client.get('/api/auth/me').status_code == 200
    assert client.post('/api/auth/logout', headers={'X-CSRF-Token':csrf,'Origin':'http://testserver'}).status_code == 200


def test_logout_revokes_replayed_cookie_and_logout_all(client):
    setup(client)
    other = TestClient(app)
    try:
        login(other)
        old = client.cookies.get(SESSION_COOKIE)
        assert client.post('/api/auth/logout').status_code == 200
        client.cookies.set(SESSION_COOKIE, old, path='/api')
        assert client.get('/api/state').status_code == 401
        assert other.get('/api/auth/me').status_code == 200
        client.cookies.clear()  # Remove the deliberately injected domain-less replay fixture.
        login(client)
        assert client.post('/api/auth/logout-all').status_code == 200
        assert other.get('/api/state').status_code == 401
    finally:
        other.close()


@pytest.mark.parametrize('expired',['idle','absolute'])
def test_session_time_limits(client, expired):
    setup(client)
    ident = digest(client.cookies.get(SESSION_COOKIE))
    with SessionLocal.begin() as db:
        row = db.get(UserSession, ident)
        if expired == 'idle':
            row.last_seen_at = now()-timedelta(minutes=31)
        else:
            row.expires_at = now()-timedelta(seconds=1)
    assert client.get('/api/auth/me').status_code == 401


def test_company_scope_catalog_details_preview_history_duplicates_and_legacy(client):
    a = company(client, name='Empresa A', rfc='AAA010101AA1', folder='C:/private-a').json()
    b = company(client, name='Empresa B', rfc='BBB020202BB2', folder='C:/private-b').json()
    first = upload(client, a['id'], 'a.xml', A).json()
    second = upload(client, b['id'], 'b.xml', A).json()
    pending = upload(client, None, 'pending.xml', A).json()
    legacy = client.post('/api/companies/'+b['id']+'/documents', headers=A, files={'file':('old.xml', XML, 'application/xml')}).json()
    setup(client)
    add_user(client, grants=[(a['id'],'read')])
    login(client, 'reader')
    state = client.get('/api/state').json()
    assert [c['id'] for c in state['companies']] == [a['id']]
    assert state['companies'][0]['folder'] == ''
    assert state['jobs'] == state['agents'] == state['audit'] == []
    assert state['current_user']['write_company_ids'] == []
    assert state['documents'][0]['id'] == first['id'] and len(state['documents']) == 1
    assert 'private-a' not in json.dumps(state) and 'private-b' not in json.dumps(state)
    catalog = client.get('/api/storage/documents').json()
    assert catalog['total'] == 1 and catalog['items'][0]['id'] == first['id']
    assert client.get('/api/storage/documents/'+first['id']+'/content?preview=true').content == XML
    assert client.get('/api/documents/'+first['id']+'/download').content == XML
    assert client.get('/api/storage/documents/'+first['id']+'/duplicates').json() == []
    for doc in [second, pending, legacy]:
        for suffix in ['', '/content', '/content?revision=1', '/content?preview=true', '/duplicates']:
            assert client.get('/api/storage/documents/'+doc['id']+suffix).status_code == 404
        assert client.get('/api/documents/'+doc['id']+'/download').status_code == 404
    assert client.post('/api/storage/documents/'+second['id']+'/verify').status_code == 404
    assert client.get('/api/storage/documents?pending=true').status_code == 403


def test_write_permission_is_separate_from_read_and_legacy_upload_is_scoped(client):
    a = company(client, name='Empresa A', rfc='AAA010101AA1').json()
    b = company(client, name='Empresa B', rfc='BBB020202BB2').json()
    setup(client)
    user = add_user(client, 'writer', [(a['id'],'read'),(b['id'],'write')])
    login(client, 'writer')
    assert upload(client, a['id']).status_code == 403
    good = upload(client, b['id'])
    assert good.status_code == 201, good.text
    assert upload(client, None).status_code == 403
    denied = client.post('/api/companies/'+a['id']+'/documents', files={'file':('a.xml', XML, 'application/xml')})
    assert denied.status_code == 404
    old = client.post('/api/companies/'+b['id']+'/documents', files={'file':('b.xml', XML, 'application/xml')})
    assert old.status_code == 201 and 'storage_name' not in old.json()
    options = client.get('/api/storage/options').json()
    assert options['can_write'] and not options['can_review'] and options['write_company_ids'] == [b['id']]
    assert client.post('/api/tasks', json={'company_id':a['id'],'title':'Denied task','due_date':'2026-11-10'}).status_code == 404
    task = client.post('/api/tasks', json={'company_id':b['id'],'title':'Allowed task','due_date':'2026-11-10'})
    assert task.status_code == 201, task.text
    assert client.put('/api/tasks/'+task.json()['id'], json={'company_id':a['id'],'title':'Move task','due_date':'2026-11-10'}).status_code == 404
    with SessionLocal() as db:
        event = db.scalar(select(StorageEvent).where(StorageEvent.document_id == good.json()['id'], StorageEvent.action == 'version_uploaded'))
        assert event.actor_id == user['id']


def test_non_admin_cannot_reach_legacy_modules_admin_functions_or_supply_identity(client):
    setup(client)
    add_user(client)
    login(client, 'reader')
    for url in ['/api/receipts', '/api/receipts/settings', '/api/receipts/clients', '/api/recopila/runs',
                '/api/organizador/runs', '/api/declara/runs', '/api/auth/users', '/api/auth/audit', '/api/storage/index-jobs']:
        assert client.get(url, headers=A).status_code == 403, url
    for url in ['/api/recopila/runs/x/file','/api/organizador/runs/x/download','/api/declara/runs/x/download','/api/receipts/x/pdf']:
        assert client.get(url).status_code == 403, url
    assert client.post('/api/companies', json={'name':'Injected','rfc':'CCC030303CC3'}).status_code == 403
    assert client.post('/api/auth/users', json={'username':'attacker','password':PASSWORD,'display_name':'Attacker','admin':True}).status_code == 403
    assert client.post('/api/storage/index-jobs', json={'source_id':'cs_internal'}).status_code == 403
    assert client.post('/api/auth/login', json={'username':'reader','password':PASSWORD,'admin':True,'company_ids':['x']}).status_code == 422
    assert client.get('/api/agent/any/claim').status_code in {404,405}
    assert client.post('/api/agent/any/claim').status_code == 401


def test_permissions_updates_deactivation_and_revocation_invalidate_sessions(client):
    a = company(client).json()
    setup(client)
    user = add_user(client, grants=[(a['id'],'read')])
    member = TestClient(app)
    try:
        login(member, 'reader')
        assert member.get('/api/state').status_code == 200
        update = client.put('/api/auth/users/'+user['id'], json={'revision':user['revision'],'display_name':'Reader',
            'admin':False,'enabled':False,'grants':[]})
        assert update.status_code == 200
        assert member.get('/api/state').status_code == 401
        assert member.post('/api/auth/login', json={'username':'reader','password':PASSWORD}).status_code == 401
        user = update.json()
        restored = client.put('/api/auth/users/'+user['id'], json={'revision':user['revision'],'display_name':'Reader',
            'admin':False,'enabled':True,'grants':[]})
        assert restored.status_code == 200
        login(member, 'reader')
        assert member.get('/api/state').json()['companies'] == []
        assert client.post('/api/auth/users/'+user['id']+'/revoke').status_code == 200
        assert member.get('/api/auth/me').status_code == 401
    finally:
        member.close()


def test_last_administrator_stale_changes_and_invalid_grants(client):
    admin = setup(client)
    user = client.get('/api/auth/users').json()[0]
    base = {'revision':user['revision'],'display_name':'Admin','admin':True,'enabled':True,'grants':[]}
    assert client.put('/api/auth/users/'+admin, json={**base,'enabled':False}).status_code == 409
    assert client.put('/api/auth/users/'+admin, json={**base,'admin':False}).status_code == 409
    reader = add_user(client)
    payload = {**base,'admin':False,'revision':reader['revision']}
    assert client.put('/api/auth/users/'+reader['id'], json={**payload,'grants':[{'company_id':'missing','access':'write'}]}).status_code == 422
    assert client.put('/api/auth/users/'+reader['id'], json=payload).status_code == 200
    assert client.put('/api/auth/users/'+reader['id'], json=payload).status_code == 409
    assert client.delete('/api/auth/users/'+reader['id']).status_code in {404,405}


def test_password_change_requires_current_password_and_revokes_all(client):
    setup(client)
    assert client.post('/api/auth/password', json={'current_password':'wrong','new_password':NEW_PASSWORD}).status_code == 401
    assert client.get('/api/auth/me').status_code == 200
    assert client.post('/api/auth/password', json={'current_password':PASSWORD,'new_password':NEW_PASSWORD}).status_code == 200
    assert client.get('/api/auth/me').status_code == 401
    assert client.post('/api/auth/login', json={'username':'admin','password':PASSWORD}).status_code == 401
    login(client, password=NEW_PASSWORD)


def test_login_throttle_persists_and_resets_after_window(client):
    setup(client)
    with SessionLocal.begin() as db:
        db.get(LoginThrottle, digest('account:admin')).attempts = 8
    assert client.post('/api/auth/login', json={'username':'admin','password':PASSWORD}).status_code == 429
    with SessionLocal.begin() as db:
        db.get(LoginThrottle, digest('account:admin')).window_started_at = now()-timedelta(minutes=16)
    login(client)


def test_validation_and_audit_do_not_echo_secrets_or_paths(client):
    setup(client)
    secret = 'Q9!AbZ'
    response = client.post('/api/auth/users', json={'username':'new','password':secret,'display_name':'New'})
    assert response.status_code == 422 and secret not in response.text
    wrong = client.post('/api/auth/login', json={'username':'not-registered','password':PASSWORD})
    assert wrong.status_code == 401 and PASSWORD not in wrong.text
    response = client.get('/api/auth/audit?kind=security&limit=100')
    assert response.status_code == 200
    assert any(row['action'] == 'login_failed' for row in response.json()['items'])
    for text in [response.text, client.get('/api/auth/users').text]:
        for protected in [PASSWORD, 'password_hash', 'csrf_hash', str(DATA)]:
            assert protected not in text
    assert client.get('/api/auth/audit?kind=storage&limit=101').status_code == 422


def test_nonlocal_http_refused_and_agent_key_cannot_be_a_user(client):
    assert client.get('/api/state', headers=G).status_code == 401
    assert client.post('/api/auth/login', headers={'Host':'example.invalid'}, json={'username':'admin','password':PASSWORD}).status_code == 400
    assert client.post('/api/auth/bootstrap', headers={**A,'Host':'example.invalid'}, json={'username':'admin','password':PASSWORD,'display_name':'Admin'}).status_code == 400


def test_local_recovery_keeps_history_and_revokes_old_session(client, monkeypatch):
    import sys
    import getpass
    from app.accounts import recover_admin
    ident = setup(client)
    answers = iter([NEW_PASSWORD, NEW_PASSWORD])
    monkeypatch.setattr(sys, 'argv', ['accounts','--username','admin'])
    monkeypatch.setattr(getpass, 'getpass', lambda _: next(answers))
    recover_admin()
    assert client.get('/api/auth/me').status_code == 401
    login(client, password=NEW_PASSWORD)
    with SessionLocal() as db:
        assert db.get(UserAccount, ident).id == ident
        assert db.scalar(select(SecurityEvent).where(SecurityEvent.actor_id == 'local_recovery'))


def test_named_user_denials_and_successes_are_audited_without_impersonation(client):
    a = company(client).json()
    setup(client)
    user = add_user(client, grants=[(a['id'],'write')])
    member = TestClient(app)
    try:
        login(member, 'reader')
        document = upload(member, a['id']).json()
        assert member.get('/api/documents/'+document['id']+'/download', headers=A).status_code == 200
        assert member.get('/api/auth/users', headers=A).status_code == 403
        with SessionLocal() as db:
            denied = db.scalar(select(SecurityEvent).where(SecurityEvent.actor_id == user['id'],
                SecurityEvent.action == 'GET /api/auth/users', SecurityEvent.code == '403'))
            read = db.scalar(select(StorageEvent).where(StorageEvent.actor_id == user['id'],
                StorageEvent.action == 'content_read', StorageEvent.document_id == document['id']))
            assert denied and read
    finally:
        member.close()


def test_administrator_reset_password_and_secure_https_cookie(client):
    setup(client)
    user = add_user(client)
    other = TestClient(app, base_url='https://testserver')
    try:
        result = login(other, 'reader')
        assert any('Secure' in h and 'HttpOnly' in h for h in result.headers.get_list('set-cookie'))
        assert other.get('/api/auth/me').status_code == 200
        response = client.put('/api/auth/users/'+user['id'], json={'revision':user['revision'],'display_name':'Reader',
            'admin':False,'enabled':True,'grants':[],'password':NEW_PASSWORD})
        assert response.status_code == 200
        assert other.get('/api/auth/me').status_code == 401
        assert other.post('/api/auth/login', json={'username':'reader','password':PASSWORD}).status_code == 401
        login(other, 'reader', NEW_PASSWORD)
    finally:
        other.close()


def test_user_grants_prevent_company_deletion_and_duplicate_names(client):
    c = company(client).json()
    setup(client)
    add_user(client, grants=[(c['id'],'read')])
    assert client.delete('/api/companies/'+c['id']).status_code == 409
    response = client.post('/api/auth/users', json={'username':'READER','display_name':'Duplicate','password':PASSWORD})
    assert response.status_code == 409


def test_background_polling_does_not_extend_idle_session(client):
    setup(client)
    ident = digest(client.cookies.get(SESSION_COOKIE))
    with SessionLocal.begin() as db:
        db.get(UserSession, ident).last_seen_at = now()-timedelta(minutes=2)
    with SessionLocal() as db:
        before = db.get(UserSession, ident).last_seen_at
    assert client.get('/api/state').status_code == 200
    with SessionLocal() as db:
        assert db.get(UserSession, ident).last_seen_at == before
    assert client.get('/api/auth/me', headers={'X-ContaSuite-Activity':'1'}).status_code == 200
    with SessionLocal() as db:
        assert db.get(UserSession, ident).last_seen_at > before


def test_account_creation_includes_state_and_grants_atomically(client):
    c = company(client).json()
    setup(client)
    created = client.post('/api/auth/users', json={'username':'disabled-admin','password':PASSWORD,
        'display_name':'Disabled','admin':True,'enabled':False,'grants':[{'company_id':c['id'],'access':'read'}]})
    assert created.status_code == 201, created.text
    assert not created.json()['enabled'] and created.json()['grants'] == [{'company_id':c['id'],'access':'read'}]
    assert client.post('/api/auth/login', json={'username':'disabled-admin','password':PASSWORD}).status_code == 401
    invalid = client.post('/api/auth/users', json={'username':'invalid-grant','password':PASSWORD,
        'display_name':'Invalid','grants':[{'company_id':'missing','access':'write'}]})
    assert invalid.status_code == 422
    with SessionLocal() as db:
        assert not db.scalar(select(UserAccount).where(UserAccount.username == 'invalid-grant'))
