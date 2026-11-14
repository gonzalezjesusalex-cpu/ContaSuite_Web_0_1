"""Bloque 2, punto 1: user roles (admin | contador | auxiliar), migration cs_0007 and role in the session."""

import pytest
from sqlalchemy import create_engine, inspect, text

from test_api import client, A  # noqa: F401  Isolated environment before app imports.
from test_accounts import PASSWORD, add_user, login, setup
from app.database import SessionLocal
from app.models import UserAccount
from app.schema_compatibility import check_schema
from app.security import Principal
from app.storage.migrate import schema_revision, upgrade_schema

HEAD = 'cs_0007_user_role'
LEGACY_USERS = """
CREATE TABLE user_accounts (
    id VARCHAR(36) PRIMARY KEY, username VARCHAR(64) UNIQUE, display_name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL, admin BOOLEAN NOT NULL, enabled BOOLEAN NOT NULL,
    revision INTEGER NOT NULL, created_at DATETIME NOT NULL
)"""


def legacy_database(path):
    """Only what cs_0007 touches: user_accounts as it was at cs_0006, with synthetic accounts."""
    engine = create_engine('sqlite:///' + str(path))
    with engine.begin() as db:
        db.exec_driver_sql('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)')
        db.exec_driver_sql("INSERT INTO alembic_version VALUES ('cs_0006_unified_baseline')")
        db.exec_driver_sql(LEGACY_USERS)
        for ident, admin in [('u-admin', 1), ('u-member', 0)]:
            db.execute(
                text('INSERT INTO user_accounts VALUES (:i, :i, :i, :h, :a, 1, 3, CURRENT_TIMESTAMP)'),
                dict(i=ident, h='unused', a=admin),
            )
    return engine


def test_migration_maps_admins_and_keeps_others_as_auxiliar(tmp_path):
    engine = legacy_database(tmp_path / 'legacy.db')
    try:
        assert schema_revision(engine) == ('cs_0006_unified_baseline', HEAD)
        upgrade_schema(engine)
        upgrade_schema(engine)  # idempotent
        assert schema_revision(engine) == (HEAD, HEAD)
        with engine.connect() as db:
            rows = db.exec_driver_sql('SELECT id, role, admin, revision FROM user_accounts ORDER BY id').all()
        assert [tuple(r) for r in rows] == [('u-admin', 'admin', 1, 3), ('u-member', 'auxiliar', 0, 3)]
    finally:
        engine.dispose()


def test_fresh_database_reaches_head_with_role_column(tmp_path):
    # user_accounts comes from cs_storage_0003, so cs_0007 adds the column here too. The CHECK constraint is
    # only added on PostgreSQL (SQLite cannot alter constraints; it is test-only); the ORM validates values.
    engine = create_engine('sqlite:///' + str(tmp_path / 'fresh.db'))
    try:
        upgrade_schema(engine)
        assert schema_revision(engine) == (HEAD, HEAD)
        assert check_schema(engine)['compatible']
        assert 'role' in {c['name'] for c in inspect(engine).get_columns('user_accounts')}
    finally:
        engine.dispose()


def test_role_and_legacy_admin_flag_stay_in_step(client):  # noqa: F811
    with SessionLocal() as db:
        legacy = UserAccount(username='legacy', display_name='L', password_hash='x', admin=True)
        member = UserAccount(username='member', display_name='M', password_hash='x')
        contador = UserAccount(username='conta', display_name='C', password_hash='x', role='contador')
        db.add_all([legacy, member, contador])
        db.commit()
        assert (legacy.role, legacy.admin) == ('admin', True)
        assert (member.role, member.admin) == ('auxiliar', False)
        assert (contador.role, contador.admin) == ('contador', False)
        legacy.admin = False
        contador.role = 'admin'
        db.commit()
        assert (legacy.role, legacy.admin) == ('auxiliar', False)
        assert (contador.role, contador.admin) == ('admin', True)
        with pytest.raises(ValueError):
            member.role = 'superusuario'


def test_principal_role_must_match_admin_flag():
    assert Principal('a', 'A', True).role == 'admin'
    assert Principal('b', 'B', False).role == 'auxiliar'
    assert Principal('c', 'C', False, role='contador').role == 'contador'
    for admin, role in [(False, 'admin'), (True, 'contador'), (False, 'root')]:
        with pytest.raises(ValueError):
            Principal('x', 'X', admin, role=role)


def test_accounts_api_uses_server_roles(client):  # noqa: F811
    setup(client)
    assert client.get('/api/auth/me').json()['role'] == 'admin'
    conta = client.post(
        '/api/auth/users',
        json={'username': 'conta', 'display_name': 'Conta', 'password': PASSWORD, 'role': 'contador'},
    )
    assert conta.status_code == 201 and conta.json()['role'] == 'contador' and not conta.json()['admin']
    assert add_user(client)['role'] == 'auxiliar'
    # Unknown roles and the retired boolean are rejected instead of being silently mapped.
    for extra in [{'role': 'root'}, {'admin': True}]:
        body = {'username': 'other', 'display_name': 'O', 'password': PASSWORD, **extra}
        assert client.post('/api/auth/users', json=body).status_code == 422
    users = {u['username']: u for u in client.get('/api/auth/users').json()}
    assert users['admin']['role'] == 'admin' and users['reader']['role'] == 'auxiliar'

    # The session carries the stored role; a non-admin role cannot grant itself anything.
    login(client, 'conta')
    me = client.get('/api/auth/me').json()
    assert me['role'] == 'contador' and not me['admin']
    assert client.get('/api/auth/users').status_code == 403
    body = {'revision': conta.json()['revision'], 'display_name': 'C', 'role': 'admin', 'enabled': True}
    assert client.put('/api/auth/users/' + conta.json()['id'], json=body).status_code == 403


def test_demoting_the_last_admin_is_refused(client):  # noqa: F811
    admin = setup(client)
    user = client.get('/api/auth/users').json()[0]
    body = {'revision': user['revision'], 'display_name': 'Admin', 'enabled': True, 'grants': []}
    for role in ['contador', 'auxiliar']:
        assert client.put('/api/auth/users/' + admin, json={**body, 'role': role}).status_code == 409
    other = client.post(
        '/api/auth/users',
        json={'username': 'second', 'display_name': 'S', 'password': PASSWORD, 'role': 'admin'},
    ).json()
    demoted = client.put('/api/auth/users/' + admin, json={**body, 'role': 'contador'})
    assert demoted.status_code == 200 and demoted.json()['role'] == 'contador' and not demoted.json()['admin']
    with SessionLocal() as db:
        assert db.get(UserAccount, admin).admin is False
        assert db.get(UserAccount, other['id']).role == 'admin'
