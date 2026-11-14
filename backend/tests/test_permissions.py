"""Bloque 2, punto 2: per-company action catalog enforced on the server (docs/BLOQUE_2_ROLES.md)."""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import PASSWORD, XML, login, setup, upload
from app.database import SessionLocal
from app.models import Company, UserCompanyAction, UserCompanyGrant
from app.permissions import ACTIONS, LEGACY_WRITE_ACTIONS, READ_ACTIONS, WRITE_ACTIONS, company_actions
from app.security import Principal

DUE = '2026-11-20'


def test_catalog_by_role():
    assert READ_ACTIONS | WRITE_ACTIONS == ACTIONS and not READ_ACTIONS & WRITE_ACTIONS
    assert company_actions('contador', True) == ACTIONS
    assert company_actions('contador', False) == READ_ACTIONS
    assert company_actions('auxiliar', False) == READ_ACTIONS
    assert company_actions('auxiliar', True) == READ_ACTIONS | LEGACY_WRITE_ACTIONS
    # Explicit actions replace the legacy reach, and unknown names are ignored.
    explicit = company_actions('auxiliar', True, {'tareas.editar', 'root', 'empresa.ver'})
    assert explicit == READ_ACTIONS | {'tareas.editar'}
    assert company_actions('auxiliar', True, set()) == READ_ACTIONS
    assert company_actions('desconocido', True) == frozenset()


def test_principal_checks():
    admin = Principal('a', 'A', True)
    assert admin.can('documentos.eliminar', 'any-company')
    aux = Principal('x', 'X', False, frozenset({'c1'}), frozenset({'c1'}), explicit_actions={'c1': frozenset()})
    assert aux.can('tareas.ver', 'c1') and not aux.can('tareas.editar', 'c1')
    assert not aux.can('tareas.ver', 'c2')
    with pytest.raises(ValueError):
        aux.can('no.existe', 'c1')
    with pytest.raises(HTTPException) as outside:
        aux.require('tareas.editar', 'c2')
    assert outside.value.status_code == 404
    with pytest.raises(HTTPException) as forbidden:
        aux.require('tareas.editar', 'c1')
    assert forbidden.value.status_code == 403
    conta = Principal('c', 'C', False, frozenset({'c1', 'c2'}), frozenset({'c1'}), role='contador')
    assert conta.can('documentos.eliminar', 'c1') and not conta.can('tareas.editar', 'c2')
    assert conta.public()['actions']['c2'] == sorted(READ_ACTIONS)


def account(c, username, role, grants=(), actions=None):
    created = c.post(
        '/api/auth/users',
        json={
            'username': username,
            'display_name': username.title(),
            'password': PASSWORD,
            'role': role,
            'grants': [{'company_id': cid, 'access': access} for cid, access in grants],
        },
    )
    assert created.status_code == 201, created.text
    if actions is not None:
        with SessionLocal.begin() as db:
            db.add_all(
                [UserCompanyAction(user_id=created.json()['id'], company_id=cid, action=a) for cid, a in actions]
            )
    return created.json()


def body(**kw):
    return {'name': 'Empresa Sintética', 'rfc': 'SIN010101AA1', **kw}


def edit_body(c, cid, **kw):
    data = next(x for x in c.get('/api/state').json()['companies'] if x['id'] == cid)
    keep = {'name', 'rfc', 'person_type', 'trade_name', 'regime', 'accountant', 'email', 'phone', 'location', 'notes'}
    return {**{k: v for k, v in data.items() if k in keep}, 'folder': data.get('folder') or '', **kw}


@pytest.fixture()
def office(client):  # noqa: F811
    a = company(client, name='Empresa A', rfc='AAA010101AA1').json()['id']
    b = company(client, name='Empresa B', rfc='BBB020202BB2').json()['id']
    other = company(client, name='Empresa C', rfc='CCC030303CC3').json()['id']
    setup(client)
    account(client, 'conta', 'contador', [(a, 'write'), (b, 'read')])
    account(client, 'aux', 'auxiliar', [(a, 'write'), (b, 'read')], actions=[(a, 'tareas.editar')])
    account(client, 'legacy', 'auxiliar', [(a, 'write')])
    return client, a, b, other


def test_contador_operates_its_companies_but_not_the_system(office):
    c, a, b, other = office
    login(c, 'conta')
    me = c.get('/api/auth/me').json()
    assert me['role'] == 'contador' and set(me['actions'][a]) == ACTIONS and set(me['actions'][b]) == READ_ACTIONS
    assert c.put('/api/companies/' + a, json=edit_body(c, a, name='A editada')).status_code == 200
    # Only an administrator assigns the responsible accountant, also when editing or registering.
    assert c.put('/api/companies/' + a, json=edit_body(c, a, accountant='Otra persona')).status_code == 403
    assert c.post('/api/companies', json=body(accountant='Yo mismo')).status_code == 403
    assert c.put('/api/companies/' + b, json=edit_body(c, b, name='B editada')).status_code == 403
    assert c.put('/api/companies/' + other, json=body(rfc='CCC030303CC3')).status_code == 404
    archive = c.put('/api/company-lifecycle/' + a, json={'archived': True, 'revision': 0})
    assert archive.status_code == 200, archive.text
    assert c.put('/api/company-lifecycle/' + b, json={'archived': True, 'revision': 0}).status_code == 403
    doc = c.post('/api/companies/' + a + '/documents', files={'file': ('a.xml', XML, 'application/xml')})
    assert doc.status_code == 201, doc.text
    assert c.delete('/api/documents/' + doc.json()['id']).status_code == 204
    for denied in [
        c.get('/api/auth/users'),
        c.post('/api/fiscal-control/catalog', json={'label': 'Nueva', 'periodicity': 'monthly'}),
        c.post('/api/jobs', json={'company_id': a, 'agent_id': 'x'}),
        c.get('/api/recopila/runs'),
    ]:
        assert denied.status_code == 403


def test_contador_registers_a_company_and_gets_write_access_without_becoming_responsible(office):
    c, *_ = office
    login(c, 'conta')
    created = c.post('/api/companies', json=body())
    assert created.status_code == 201, created.text
    cid = created.json()['id']
    with SessionLocal() as db:
        assert db.get(Company, cid).accountant == 'Sin asignar'
        conta = db.scalar(select(UserCompanyGrant).where(UserCompanyGrant.company_id == cid))
        assert conta.access == 'write'
    login(c, 'conta')  # grants are read at each request; a new login is not required but must also work
    assert c.post('/api/tasks', json={'company_id': cid, 'title': 'Alta', 'due_date': DUE}).status_code == 201


def test_auxiliar_has_only_its_explicit_actions(office):
    c, a, b, other = office
    login(c, 'aux')
    me = c.get('/api/auth/me').json()
    assert me['role'] == 'auxiliar' and set(me['actions'][a]) == READ_ACTIONS | {'tareas.editar'}
    assert c.get('/api/state').status_code == 200
    assert c.post('/api/tasks', json={'company_id': a, 'title': 'Permitida', 'due_date': DUE}).status_code == 201
    for denied in [
        c.post('/api/tasks', json={'company_id': b, 'title': 'Lectura', 'due_date': DUE}),
        c.post('/api/obligations', json={'company_id': a, 'title': 'IVA', 'period': '2026-10', 'due_date': DUE}),
        c.post('/api/companies/' + a + '/documents', files={'file': ('a.xml', XML, 'application/xml')}),
        upload(c, a),
        c.put('/api/companies/' + a, json=edit_body(c, a, name='No')),
        c.put('/api/company-lifecycle/' + a, json={'archived': True, 'revision': 0}),
        c.post('/api/companies', json=body()),
    ]:
        assert denied.status_code == 403, denied.text
    assert c.post('/api/tasks', json={'company_id': other, 'title': 'Ajena', 'due_date': DUE}).status_code == 404
    assert c.get('/api/storage/options').json()['write_company_ids'] == []


def test_migrated_auxiliar_keeps_its_previous_write_reach(office):
    c, a, *_ = office
    login(c, 'legacy')
    assert c.post('/api/tasks', json={'company_id': a, 'title': 'Antes', 'due_date': DUE}).status_code == 201
    doc = c.post('/api/companies/' + a + '/documents', files={'file': ('a.xml', XML, 'application/xml')})
    assert doc.status_code == 201
    # What only administrators could do before stays out of reach.
    assert c.delete('/api/documents/' + doc.json()['id']).status_code == 403
    assert c.put('/api/companies/' + a, json=edit_body(c, a, name='No')).status_code == 403
    assert c.post('/api/companies', json=body()).status_code == 403


def test_actions_cannot_be_supplied_by_the_client(office):
    c, a, *_ = office
    login(c, 'aux')
    # Unknown fields are rejected; actions only come from the server-side tables.
    sneaky = c.post(
        '/api/tasks',
        json={'company_id': a, 'title': 'x', 'due_date': DUE, 'actions': ['obligaciones.editar']},
    )
    assert sneaky.status_code in {403, 422}
    assert (
        c.post(
            '/api/obligations',
            headers={'X-ContaSuite-Role': 'admin'},
            json={'company_id': a, 'title': 'IVA', 'period': '2026-10', 'due_date': DUE},
        ).status_code
        == 403
    )
