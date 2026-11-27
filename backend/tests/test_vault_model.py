"""Renovación del gestor de contraseñas, fase 2: types, default users, certificate classes, permissions and log."""

import importlib.util
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update

from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import add_user, login, setup
from app.credential_models import audit, certificates, credentials
from app.database import SessionLocal, engine
from app.models import Company, now

RFC = 'SSI260101AB1'
MASTER = 'Maestra-Sintetica-2026!'


def open_vault(c):
    made = c.post('/api/credentials/vault/setup', json={'password': MASTER, 'confirm': MASTER})
    assert made.status_code == 201, made.text


def office(c):
    cid = company(c, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(c)
    open_vault(c)
    with SessionLocal() as db:
        db.execute(
            update(Company).where(Company.id == cid).values(employer_registration='Y1234567890', email='a@b.test')
        )
        db.commit()
    return cid


def secret(c, cid, **body):
    made = c.post(f'/api/credentials/companies/{cid}/secrets', json={'secret': 'Secreto-Sintetico-2!', **body})
    assert made.status_code == 200, made.text
    return made.json()['id']


def row(ident):
    with SessionLocal() as db:
        return db.execute(select(credentials).where(credentials.c.id == ident)).mappings().first()


# ---------------------------------------------------------------- types and default users


def test_types_and_default_user_by_type(client):  # noqa: F811
    cid = office(client)
    expected = {
        'SAT_CIEC': ('sat_password', RFC),
        'INFONAVIT': ('infonavit', RFC),
        'IMSS_IDSE': ('idse', 'Y1234567890'),
        'SIPARE': ('sipare', 'Y1234567890'),
        'CORREO': ('email', 'a@b.test'),
        'OTRO': ('other', None),
    }
    for kind, (service, user) in expected.items():
        saved = row(secret(client, cid, kind=kind))
        assert (saved['kind'], saved['service_id'], saved['username']) == (kind, service, user), kind
        assert saved['updated_by'] and saved['requires_review'] is False
    # The default user can be edited; a portal of the catalog still gives its type.
    own = row(secret(client, cid, kind='SAT_CIEC', username='OTRO010101AB1'))
    assert own['username'] == 'OTRO010101AB1'
    assert row(secret(client, cid, service_id='idse_password'))['kind'] == 'IMSS_IDSE'
    assert row(secret(client, cid, service_id='fiel_password'))['kind'] == 'LLAVE'
    assert client.post(f'/api/credentials/companies/{cid}/secrets', json={'secret': 'x-y-z-1'}).status_code == 422
    listed = client.get('/api/credentials/vault').json()['items']
    assert {i['kind'] for i in listed} >= {'SAT_CIEC', 'CORREO', 'LLAVE'}


# ---------------------------------------------------------------- certificates


def add_cert(c, cid, **body):
    return c.post(f'/api/credentials/companies/{cid}/certificates', json=body)


def certs(cid):
    with SessionLocal() as db:
        return {r['id']: r for r in db.execute(select(certificates).where(certificates.c.company_id == cid)).mappings()}


def test_one_active_fiel_per_class_and_history(client):  # noqa: F811
    cid = office(client)
    first = add_cert(client, cid, kind='fiel').json()['id']
    rep = add_cert(client, cid, kind='fiel', holder='legal_rep').json()['id']
    refused = add_cert(client, cid, kind='fiel')
    assert refused.status_code == 409 and 'reemplazas' in refused.json()['detail']
    second = add_cert(client, cid, kind='fiel', replace=True).json()['id']
    csd = [add_cert(client, cid, kind='csd', branch=b).json()['id'] for b in ('Matriz', 'Sucursal Norte')]
    rows = certs(cid)
    assert rows[first]['active'] is False and rows[first]['replaced_by'] == second
    assert rows[second]['active'] and rows[second]['cert_class'] == 'FIEL_EMPRESA'
    assert rows[rep]['active'] and rows[rep]['cert_class'] == 'FIEL_REPRESENTANTE' and rows[rep]['holder_rfc'] is None
    assert all(rows[i]['active'] and rows[i]['cert_class'] == 'CSD' for i in csd)  # several CSD, one per branch
    assert {rows[i]['branch'] for i in csd} == {'Matriz', 'Sucursal Norte'}
    shown = client.get(f'/api/credentials/companies/{cid}').json()['certificates']
    assert {c['id']: c['active'] for c in shown}[first] is False


# ---------------------------------------------------------------- permissions


def test_permissions_by_role(client):  # noqa: F811
    cid = office(client)
    ident = secret(client, cid, kind='SAT_CIEC')
    state = client.get('/api/state').json()
    assert state['vault_access'] is True
    aux = add_user(client, 'aux', grants=[(cid, 'write')])
    aux_id = aux['id'] if isinstance(aux, dict) else aux
    add_user(client, 'otro', grants=[(cid, 'write')])
    code = client.post('/api/credentials/vault/members', json={'user_id': aux_id}).json()['temporary_code']
    client.post(f'/api/credentials/companies/{cid}/secrets/{ident}/reveal', json={'action': 'view'})

    # Someone without a vault key does not see the module at all.
    client.cookies.clear()
    login(client, 'otro')
    assert client.get('/api/state').json()['vault_access'] is False
    assert client.get('/api/credentials/vault').status_code == 403
    assert client.get(f'/api/credentials/companies/{cid}').status_code == 403

    # An authorized person views and copies, but does not add, edit, delete, import or export.
    client.cookies.clear()
    login(client, 'aux')
    assert client.get('/api/state').json()['vault_access'] is True
    assert client.post('/api/credentials/vault/unlock', json={'password': code}).status_code == 200
    listed = client.get('/api/credentials/vault').json()
    assert [i['can_reveal'] for i in listed['items']] == [True] and not listed['items'][0]['can_modify']
    shown = client.post(f'/api/credentials/companies/{cid}/secrets/{ident}/reveal', json={'action': 'copy'})
    assert shown.status_code == 200 and shown.json()['secret'] == 'Secreto-Sintetico-2!'
    assert (
        client.post(f'/api/credentials/companies/{cid}/secrets', json={'kind': 'OTRO', 'secret': 'a-b-c-1'}).status_code
        == 403
    )
    assert client.delete(f'/api/credentials/companies/{cid}/secrets/{ident}?revision=1').status_code == 403
    assert client.post(f'/api/credentials/companies/{cid}/certificates', json={'kind': 'fiel'}).status_code == 403
    assert client.post('/api/credentials/export', json={'reason': 'respaldo', 'password': 'x'}).status_code == 403
    preview = client.post('/api/credentials/import/read', files={'file': ('a.xlsx', b'PK', 'application/octet-stream')})
    assert preview.status_code == 403
    # The log shows only their own actions (the administrator's view of the same secret is not listed).
    log = client.get(f'/api/credentials/companies/{cid}/history').json()
    assert log and {r['actor_id'] for r in log} == {aux_id}
    assert 'COPIAR' in {r['kind'] for r in log}


# ---------------------------------------------------------------- log


def test_log_rows_carry_the_spec_action_and_the_computer(client):  # noqa: F811
    cid = office(client)
    ident = secret(client, cid, kind='SAT_CIEC')
    client.post(f'/api/credentials/companies/{cid}/secrets/{ident}/reveal', json={'action': 'view'})
    client.post('/api/credentials/vault/lock')
    client.post('/api/credentials/vault/unlock', json={'password': 'incorrecta-123'})
    with SessionLocal() as db:
        rows = list(db.execute(select(audit).order_by(audit.c.created_at)).mappings())
    kinds = [r['kind'] for r in rows if r['kind']]
    assert {'CREAR', 'VER', 'DESBLOQUEO_FALLIDO'} <= set(kinds)
    seen = next(r for r in rows if r['kind'] == 'VER')
    assert seen['resource_type'] == 'credencial' and seen['record_id'] == ident
    assert seen['client'] and 'testclient' in seen['client']
    assert 'Secreto-Sintetico' not in str(rows)


# ---------------------------------------------------------------- migration of the data that already exists


def test_migration_fills_types_classes_and_incomplete_certificates(client):  # noqa: F811
    cid = office(client)
    sat, fiel_password = secret(client, cid, kind='SAT_CIEC'), secret(client, cid, service_id='fiel_password')
    old_a, old_b = str(uuid4()), str(uuid4())
    with SessionLocal() as db:
        # As before cs_0024: no type, no class, no active flag.
        db.execute(update(credentials).values(kind=None, requires_review=None))
        db.execute(certificates.delete().where(certificates.c.company_id == cid))
        for ident, year in ((old_a, 2027), (old_b, 2029)):
            db.execute(
                certificates.insert().values(
                    id=ident,
                    company_id=cid,
                    kind='fiel',
                    rfc=RFC,
                    holder='company',
                    origin='vault',
                    reviewed_at=now(),
                    notes='',
                    revision=1,
                    fingerprint=ident.replace('-', ''),
                    valid_from=now(),
                    valid_until=now().replace(year=year),
                )
            )
        db.execute(audit.update().values(kind=None, resource_type=None))
        db.commit()
    spec = importlib.util.spec_from_file_location(
        'cs_0024', Path(__file__).parents[1] / 'migrations' / 'versions' / '0024_vault_types_classes.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
    assert row(sat)['kind'] == 'SAT_CIEC' and row(fiel_password)['kind'] == 'LLAVE'
    rows = certs(cid)
    assert rows[old_b]['active'] and not rows[old_a]['active'] and rows[old_a]['replaced_by'] == old_b
    incomplete = [r for r in rows.values() if r['key_password_id'] == fiel_password]
    assert len(incomplete) == 1 and incomplete[0]['notes'] == 'Faltan .cer y .key'
    assert incomplete[0]['cert_class'] == 'FIEL_EMPRESA'
    with SessionLocal() as db:
        assert 'CREAR' in set(db.scalars(select(audit.c.kind)))
