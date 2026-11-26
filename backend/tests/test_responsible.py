"""Bloque 2, points 5-7: responsible accountant by user, reconciliation, company history and filters."""

import pytest
from sqlalchemy import create_engine, select

from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import login, setup
from test_permissions import account, edit_body
from app.database import SessionLocal
from app.models import Audit, Company, UserAccount, UserCompanyGrant
from app.storage.migrate import _upgrade, upgrade_schema


@pytest.fixture()
def office(client):  # noqa: F811
    a = company(client, name='Empresa A', rfc='AAA010101AA1', accountant='Ana Pérez').json()['id']
    b = company(client, name='Empresa B', rfc='BBB020202BB2', accountant='Luis Gómez').json()['id']
    c = company(client, name='Empresa C', rfc='CCC030303CC3', accountant='Nadie Conocido').json()['id']
    with SessionLocal.begin() as db:
        # What cs_0011 does on an existing database: keep the free text as legacy, assign nobody.
        for company_row in db.scalars(select(Company)):
            company_row.accountant_legacy = company_row.accountant
    setup(client)
    ana = account(client, 'ana', 'contador', [(b, 'read')])
    luis = account(client, 'luis', 'contador')
    luis2 = account(client, 'luis2', 'contador')
    with SessionLocal.begin() as db:
        # Two accountants share a display name: the reconciliation must not pick one by itself.
        for user_id, name in [(ana['id'], 'Ana Pérez'), (luis['id'], 'Luis Gómez'), (luis2['id'], 'Luis Gómez')]:
            db.get(UserAccount, user_id).display_name = name
    account(client, 'aux', 'auxiliar', [(a, 'read')], actions=[])
    off = account(client, 'off', 'contador')
    edit = {'revision': off['revision'], 'display_name': 'Off', 'role': 'contador', 'enabled': False, 'grants': []}
    assert client.put('/api/auth/users/' + off['id'], json=edit).status_code == 200
    return client, {'a': a, 'b': b, 'c': c}, {'ana': ana['id'], 'luis': luis['id'], 'off': off['id']}


def assign(c, cid, new, current=None, previous=None):
    body = {'current_accountant_id': current, 'accountant_id': new}
    if previous:
        body['previous_access'] = previous
    return c.put('/api/responsible/companies/' + cid, json=body)


def test_candidates_are_active_accountants_only(office):
    c, _, users = office
    names = {r['username'] for r in c.get('/api/responsible/candidates').json()}
    assert names == {'ana', 'luis', 'luis2'}
    login(c, 'ana')
    assert c.get('/api/responsible/candidates').status_code == 403


def test_assign_change_and_remove_with_explicit_previous_access(office):
    c, companies, users = office
    a, b = companies['a'], companies['b']
    for wrong in [users['off'], 'missing']:
        assert assign(c, a, wrong).status_code == 422  # disabled or unknown accounts are refused
    admin_id = c.get('/api/auth/me').json()['id']
    assert assign(c, a, admin_id).status_code == 422  # an administrator is never responsible

    first = assign(c, b, users['ana'])
    assert first.status_code == 200, first.text
    assert first.json()['accountant'] == 'Ana Pérez' and any('escritura' in n for n in first.json()['notices'])
    with SessionLocal() as db:
        assert db.get(UserCompanyGrant, (users['ana'], b)).access == 'write'  # read grant upgraded

    assert assign(c, b, users['luis'], current=None).status_code == 409  # stale view of the current one
    assert assign(c, b, users['luis'], current=users['ana']).status_code == 422  # previous access not chosen
    changed = assign(c, b, users['luis'], current=users['ana'], previous='read')
    assert changed.status_code == 200, changed.text
    with SessionLocal() as db:
        assert db.get(UserCompanyGrant, (users['ana'], b)).access == 'read'
        assert db.get(UserCompanyGrant, (users['luis'], b)).access == 'write'
    removed = assign(c, b, None, current=users['luis'], previous='remove')
    assert removed.status_code == 200 and removed.json()['accountant'] == 'Sin asignar'
    with SessionLocal() as db:
        assert db.get(UserCompanyGrant, (users['luis'], b)) is None
        rows = db.scalars(select(Audit).where(Audit.company_id == b, Audit.action.like('Responsable%'))).all()
    assert [r.action for r in sorted(rows, key=lambda r: r.created_at)] == [
        'Responsable asignado',
        'Responsable cambiado',
        'Responsable retirado',
    ]
    assert all(r.actor_id == admin_id for r in rows)
    change = next(r for r in rows if r.action == 'Responsable cambiado').changes
    assert change['responsable']['before']['display_name'] == 'Ana Pérez'
    assert change['responsable']['after']['display_name'] == 'Luis Gómez'
    assert change['acceso_anterior'] == {'after': 'read'}


def test_responsible_rules_in_other_screens(office):
    c, companies, users = office
    a = companies['a']
    assert assign(c, a, users['ana']).status_code == 200
    # With a linked responsible the text is no longer edited as company data.
    assert c.put('/api/companies/' + a, json=edit_body(c, a, accountant='Otro texto')).status_code == 422
    assert c.put('/api/companies/' + a, json=edit_body(c, a, name='A editada')).status_code == 200
    # A responsible accountant keeps its role until its companies are reassigned.
    ana = next(u for u in c.get('/api/auth/users').json() if u['username'] == 'ana')
    demote = {
        'revision': ana['revision'],
        'display_name': 'Ana Pérez',
        'role': 'auxiliar',
        'enabled': True,
        'grants': [],
    }
    assert c.put('/api/auth/users/' + ana['id'], json=demote).status_code == 409
    # Renovación del gestor, fase 1: the vault opens with a master password; Ana gets a temporary code.
    master = 'Maestra-Sintetica-2026!'
    assert c.post('/api/credentials/vault/setup', json={'password': master, 'confirm': master}).status_code == 201
    code = c.post('/api/credentials/vault/members', json={'user_id': ana['id']}).json()['temporary_code']
    login(c, 'ana')
    assert assign(c, a, users['luis'], current=users['ana'], previous='keep').status_code == 403
    assert c.get('/api/credentials/companies/' + a).status_code == 423  # locked: no company data
    assert c.post('/api/credentials/vault/unlock', json={'password': code}).status_code == 200
    # Credentials: the responsible holds them (except reveal); another accountant with write does not.
    overview = c.get('/api/credentials/companies/' + a)
    assert overview.status_code == 200, overview.text
    assert 'reveal' not in overview.json()['permissions'] and 'certificates' in overview.json()['permissions']
    login(c, 'admin')
    account(c, 'otro', 'contador', [(a, 'write')])
    login(c, 'otro')
    assert c.get('/api/credentials/companies/' + a).status_code == 403


def test_reconciliation_proposes_by_exact_name_and_applies_only_what_is_confirmed(office):
    c, companies, users = office
    rows = {r['company']: r for r in c.get('/api/responsible/reconciliation').json()}
    assert rows['Empresa A']['status'] == 'match' and rows['Empresa A']['candidates'][0]['id'] == users['ana']
    assert rows['Empresa B']['status'] == 'ambiguous' and len(rows['Empresa B']['candidates']) == 2
    assert rows['Empresa C']['status'] == 'none'
    with SessionLocal() as db:
        assert db.get(Company, companies['a']).accountant_id is None  # proposing assigns nothing
    applied = c.post(
        '/api/responsible/reconciliation/apply',
        json={'items': [{'company_id': companies['a'], 'accountant_id': users['ana']}]},
    )
    assert applied.status_code == 200, applied.text
    again = c.post(
        '/api/responsible/reconciliation/apply',
        json={'items': [{'company_id': companies['a'], 'accountant_id': users['luis']}]},
    )
    assert again.status_code == 409
    with SessionLocal() as db:
        assert db.get(Company, companies['a']).accountant_legacy == 'Ana Pérez'  # kept until confirmed
    assert c.post('/api/responsible/reconciliation/retire', json={'company_ids': [companies['a']]}).status_code == 200
    with SessionLocal() as db:
        assert db.get(Company, companies['a']).accountant_legacy is None
    login(c, 'ana')
    assert c.get('/api/responsible/reconciliation').status_code == 403


def test_history_state_and_directory_filters(office):
    c, companies, users = office
    a, b = companies['a'], companies['b']
    assert assign(c, a, users['ana']).status_code == 200
    login(c, 'aux')
    history = c.get('/api/companies/' + a + '/history')
    assert history.status_code == 200
    first = next(r for r in history.json() if r['action'] == 'Responsable asignado')
    assert (
        first['actor'] == 'Administración de prueba' and first['changes']['responsable']['after']['id'] == users['ana']
    )
    assert c.get('/api/companies/' + b + '/history').status_code == 404
    login(c, 'admin')
    state = c.get('/api/state').json()
    assert state['responsibles'] == [{'id': users['ana'], 'display_name': 'Ana Pérez', 'enabled': True}]
    names = lambda q: {x['name'] for x in c.get('/api/company-lifecycle?' + q).json()['companies']}  # noqa: E731
    assert names('responsible=none') == {'Empresa B', 'Empresa C'}
    assert names('responsible=' + users['ana']) == {'Empresa A'}
    login(c, 'ana')
    assert names('responsible=mine') == {'Empresa A'}


def test_migration_keeps_free_text_as_legacy_and_assigns_nobody(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'old.db'))
    try:
        _upgrade(engine, 'cs_0010_audit_actor')
        with engine.begin() as db:
            for ident, text in [('c1', 'Ana Pérez'), ('c2', 'Sin asignar'), ('c3', '  ')]:
                db.exec_driver_sql(
                    "INSERT INTO companies (id, is_demo, name, rfc, person_type, trade_name, regime, accountant, "
                    "email, phone, location, folder, notes, created_at) VALUES (?, 0, ?, ?, 'Moral', '', '601', ?, "
                    "'', '', '', '', '', CURRENT_TIMESTAMP)",
                    (ident, ident, ident.upper() + '0101AA1', text),
                )
        upgrade_schema(engine)
        upgrade_schema(engine)
        with engine.connect() as db:
            rows = db.exec_driver_sql(
                'SELECT id, accountant, accountant_id, accountant_legacy FROM companies ORDER BY id'
            ).all()
        assert [tuple(r) for r in rows] == [
            ('c1', 'Ana Pérez', None, 'Ana Pérez'),
            ('c2', 'Sin asignar', None, None),
            ('c3', '  ', None, None),
        ]
    finally:
        engine.dispose()
