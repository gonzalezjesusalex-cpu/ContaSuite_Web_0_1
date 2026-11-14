"""Bloque 2, punto 3: an accountant manages the auxiliaries of its companies, without escalation."""

from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import PASSWORD, login, setup
from test_permissions import account
from app.database import SessionLocal
from app.models import UserCompanyAction
from app.permissions import LEGACY_WRITE_ACTIONS, TEMPLATES
from sqlalchemy import select

DUE = '2026-11-20'


def aux(username, grants):
    return {
        'username': username,
        'display_name': username.title(),
        'password': PASSWORD,
        'role': 'auxiliar',
        'grants': grants,
    }


def office(c):
    a = company(c, name='Empresa A', rfc='AAA010101AA1').json()['id']
    b = company(c, name='Empresa B', rfc='BBB020202BB2').json()['id']
    other = company(c, name='Empresa C', rfc='CCC030303CC3').json()['id']
    setup(c)
    account(c, 'conta', 'contador', [(a, 'write'), (b, 'read')])
    account(c, 'conta2', 'contador', [(other, 'write')])
    return a, b, other


def test_accountant_creates_auxiliaries_with_templates_only_in_its_companies(client):  # noqa: F811
    a, b, other = office(client)
    login(client, 'conta')
    catalog = client.get('/api/auth/catalog').json()
    assert {t['id'] for t in catalog['templates']} == set(TEMPLATES)
    captura = sorted(TEMPLATES['captura']['actions'])
    created = client.post(
        '/api/auth/users', json=aux('apoyo', [{'company_id': a, 'access': 'read', 'actions': captura}])
    )
    assert created.status_code == 201, created.text
    user = created.json()
    assert user['role'] == 'auxiliar' and user['grants'] == [{'company_id': a, 'access': 'write', 'actions': captura}]

    login(client, 'apoyo')
    assert client.post('/api/tasks', json={'company_id': a, 'title': 'Captura', 'due_date': DUE}).status_code == 201
    obligation = {'company_id': a, 'title': 'IVA', 'period': '2026-10', 'due_date': DUE}
    assert client.post('/api/obligations', json=obligation).status_code == 403
    assert client.get('/api/auth/users').status_code == 403

    login(client, 'conta')
    denied = [
        # Other roles, read-only or foreign companies, unknown or unheld actions, or no company at all.
        ({**aux('extra1', [{'company_id': a, 'access': 'read'}]), 'role': 'contador'}, 403),
        ({**aux('extra2', [{'company_id': a, 'access': 'read'}]), 'role': 'admin'}, 403),
        (aux('extra3', [{'company_id': b, 'access': 'read', 'actions': []}]), 403),
        (aux('extra4', [{'company_id': other, 'access': 'read', 'actions': []}]), 403),
        (aux('extra5', [{'company_id': a, 'access': 'read', 'actions': ['root.todo']}]), 422),
        (aux('extra6', []), 422),
    ]
    for payload, code in denied:
        assert client.post('/api/auth/users', json=payload).status_code == code, payload['username']


def test_accountant_sees_and_edits_only_its_part_of_an_auxiliary(client):  # noqa: F811
    a, b, other = office(client)
    shared = account(client, 'shared', 'auxiliar', [(a, 'read'), (other, 'read')], actions=[])
    solo = account(client, 'solo', 'auxiliar', [(a, 'read')], actions=[])
    account(client, 'ajeno', 'auxiliar', [(other, 'read')], actions=[])
    login(client, 'conta')
    listed = {u['username']: u for u in client.get('/api/auth/users').json()}
    assert set(listed) == {'shared', 'solo'}
    assert [g['company_id'] for g in listed['shared']['grants']] == [a]  # the other company stays hidden

    base = {'role': 'auxiliar', 'enabled': True}
    edit = {
        **base,
        'revision': listed['shared']['revision'],
        'display_name': 'Shared',
        'grants': [{'company_id': a, 'access': 'read', 'actions': ['tareas.editar']}],
    }
    assert client.put('/api/auth/users/' + shared['id'], json=edit).status_code == 200
    with SessionLocal() as db:
        kept = db.scalars(select(UserCompanyAction).where(UserCompanyAction.user_id == shared['id'])).all()
        assert {(r.company_id, r.action) for r in kept} == {(a, 'tareas.editar')}
    login(client, 'admin')
    grants = {
        g['company_id']
        for g in next(u for u in client.get('/api/auth/users').json() if u['id'] == shared['id'])['grants']
    }
    assert grants == {a, other}  # the grant outside the accountant's companies survived its edit

    login(client, 'conta')
    current = {u['username']: u for u in client.get('/api/auth/users').json()}
    # The account itself is shared: name, state and password only change when every company is its own.
    rename = {**edit, 'revision': current['shared']['revision'], 'display_name': 'Otro nombre'}
    assert client.put('/api/auth/users/' + shared['id'], json=rename).status_code == 403
    disable = {
        **base,
        'revision': current['solo']['revision'],
        'display_name': 'Solo',
        'enabled': False,
        'grants': [{'company_id': a, 'access': 'read', 'actions': []}],
    }
    assert client.put('/api/auth/users/' + solo['id'], json=disable).status_code == 200
    assert client.post('/api/auth/login', json={'username': 'solo', 'password': PASSWORD}).status_code == 401
    promote = {**disable, 'revision': disable['revision'] + 1, 'role': 'contador', 'grants': []}
    assert client.put('/api/auth/users/' + solo['id'], json=promote).status_code == 403
    ajeno = next(u for u in client.get('/api/auth/users').json() if u['username'] == 'solo')
    assert ajeno['enabled'] is False
    with SessionLocal() as db:
        ajeno_id = db.scalar(select(UserCompanyAction.user_id).limit(1))
    assert ajeno_id is not None
    for ident in [account_id(client, 'ajeno')]:
        assert client.post('/api/auth/users/' + ident + '/revoke').status_code == 404


def account_id(c, username):
    from app.models import UserAccount

    with SessionLocal() as db:
        return db.scalar(select(UserAccount.id).where(UserAccount.username == username))


def test_admin_assigns_actions_and_legacy_write_becomes_explicit(client):  # noqa: F811
    a, *_ = office(client)
    created = client.post('/api/auth/users', json=aux('legado', [{'company_id': a, 'access': 'write'}]))
    assert created.status_code == 201
    assert created.json()['grants'][0]['actions'] == sorted(LEGACY_WRITE_ACTIONS)
    conta = next(u for u in client.get('/api/auth/users').json() if u['username'] == 'conta')
    # Actions are only for auxiliaries; changing the role clears them.
    bad = {
        'revision': conta['revision'],
        'display_name': 'Conta',
        'role': 'contador',
        'enabled': True,
        'grants': [{'company_id': a, 'access': 'write', 'actions': ['tareas.editar']}],
    }
    assert client.put('/api/auth/users/' + conta['id'], json=bad).status_code == 422
    user = created.json()
    to_conta = {
        'revision': user['revision'],
        'display_name': 'Legado',
        'role': 'contador',
        'enabled': True,
        'grants': [{'company_id': a, 'access': 'write'}],
    }
    assert client.put('/api/auth/users/' + user['id'], json=to_conta).status_code == 200
    with SessionLocal() as db:
        assert not db.scalars(select(UserCompanyAction).where(UserCompanyAction.user_id == user['id'])).all()
