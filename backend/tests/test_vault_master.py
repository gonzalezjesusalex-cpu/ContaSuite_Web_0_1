"""Renovación del gestor de contraseñas, fase 1: master password, recovery code, unlock, lock and migration."""

import base64
import json
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update

from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import PASSWORD, add_user, login, setup
from app import vault_session
from app.credential_crypto import (
    VaultCipher,
    VaultLocked,
    normalize_recovery,
    recovery_code,
    unwrap_data_key,
    wrap_data_key,
)
from app.credential_models import audit, credentials, files, vault_config, vault_keys, versions
from app.database import SessionLocal
from app.models import now

RFC = 'SSI260101AB1'
MASTER = 'Maestra-Sintetica-2026!'
NEW_MASTER = 'Otra-Maestra-Sintetica-7#'
SECRET = 'Secreto-Sintetico-Fase1!'


def state(c):
    return c.get('/api/credentials/vault/state').json()


def create_vault(c, password=MASTER):
    made = c.post('/api/credentials/vault/setup', json={'password': password, 'confirm': password})
    assert made.status_code == 201, made.text
    return made.json()['recovery_code']


def unlock(c, **body):
    return c.post('/api/credentials/vault/unlock', json=body)


def actions():
    with SessionLocal() as db:
        return list(db.scalars(select(audit.c.action).order_by(audit.c.created_at)))


# ---------------------------------------------------------------- cryptography


def test_data_key_wrap_needs_the_right_password_row_and_key_id():
    data_key, row_id = os.urandom(32), str(uuid4())
    row = {'id': row_id, **wrap_data_key(data_key, MASTER, row_id, 'dk-1')}
    assert MASTER not in json.dumps(row) and base64.b64encode(data_key).decode() not in json.dumps(row)
    assert unwrap_data_key(row, MASTER, 'dk-1') == data_key
    for bad in [
        ({**row}, 'otra-contraseña', 'dk-1'),
        ({**row, 'id': 'otra-fila'}, MASTER, 'dk-1'),
        (row, MASTER, 'dk-2'),
    ]:
        with pytest.raises(VaultLocked):
            unwrap_data_key(*bad)
    cipher = VaultCipher({'dk-1': data_key}, 'dk-1')
    sealed = cipher.seal(SECRET, 'empresa-a', 'registro-a')
    with pytest.raises(VaultLocked):  # another data key
        VaultCipher({'dk-1': os.urandom(32)}, 'dk-1').open(
            sealed, 'empresa-a', 'registro-a', authorize_recent=lambda: True
        )
    with pytest.raises(VaultLocked):  # the secret cannot move to another company
        cipher.open(sealed, 'empresa-b', 'registro-a', authorize_recent=lambda: True)


def test_recovery_code_format_and_normalization():
    code = recovery_code()
    assert len(code) == 29 and code.count('-') == 5 and recovery_code() != code
    assert normalize_recovery(code.lower().replace('-', ' ')) == code


# ---------------------------------------------------------------- setup, unlock and lock


def test_vault_starts_locked_and_shows_nothing(client):  # noqa: F811
    cid = company(client, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(client)
    first = state(client)
    assert first['configured'] is False and first['can_setup'] and not first['unlocked']
    for path in (
        '/api/credentials/vault',
        f'/api/credentials/companies/{cid}',
        f'/api/credentials/companies/{cid}/history',
    ):
        locked = client.get(path)
        assert locked.status_code == 423 and 'Servicios' not in locked.text, path
    assert unlock(client, password=MASTER).status_code == 409  # not configured yet


def test_setup_rules_recovery_code_and_no_plain_text(client):  # noqa: F811
    cid = company(client, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(client)
    short = client.post('/api/credentials/vault/setup', json={'password': 'corta', 'confirm': 'corta'})
    assert short.status_code == 422
    mismatch = client.post('/api/credentials/vault/setup', json={'password': MASTER, 'confirm': MASTER + 'x'})
    assert mismatch.status_code == 422
    code = create_vault(client)
    assert state(client)['unlocked'] and state(client)['seconds_left'] > 0
    assert client.post('/api/credentials/vault/setup', json={'password': MASTER, 'confirm': MASTER}).status_code == 409
    ident = client.post(
        f'/api/credentials/companies/{cid}/secrets', json={'service_id': 'sat_password', 'secret': SECRET}
    ).json()['id']
    # A direct look at the database never finds the master password, the recovery code or the secret.
    with SessionLocal() as db:
        dump = ' '.join(
            str(list(db.execute(text(f'SELECT * FROM {table}'))))
            for table in ('vault_config', 'vault_keys', 'vault_credentials', 'vault_versions', 'vault_audit')
        )
    assert all(v not in dump for v in (MASTER, code, SECRET))
    # «Bloquear ahora», then the recovery code (typed loosely) opens it and asks for a new master password.
    assert client.post('/api/credentials/vault/lock').json() == {'unlocked': False}
    assert client.post(f'/api/credentials/companies/{cid}/secrets/{ident}/reveal').status_code == 423
    assert unlock(client, recovery_code='AAAA-BBBB-CCCC-DDDD-EEEE-FFFF').status_code == 403
    opened = unlock(client, recovery_code=code.lower().replace('-', ' '))
    assert opened.status_code == 200 and opened.json()['must_change']
    assert client.post(f'/api/credentials/companies/{cid}/secrets/{ident}/reveal').json()['secret'] == SECRET
    changed = client.post('/api/credentials/vault/password', json={'password': NEW_MASTER, 'confirm': NEW_MASTER})
    assert changed.status_code == 200 and not changed.json()['must_change']
    client.post('/api/credentials/vault/lock')
    assert unlock(client, password=MASTER).status_code == 403
    assert unlock(client, password=NEW_MASTER).status_code == 200
    # Changing it again needs the current one; a new recovery code replaces the old one.
    again = client.post('/api/credentials/vault/password', json={'password': MASTER, 'confirm': MASTER})
    assert again.status_code == 403
    fresh = client.post('/api/credentials/vault/recovery', json={'password': NEW_MASTER}).json()['recovery_code']
    client.post('/api/credentials/vault/lock')
    assert unlock(client, recovery_code=code).status_code == 403
    assert unlock(client, recovery_code=fresh).status_code == 200
    logged = actions()
    assert {'vault_setup', 'vault_unlocked', 'vault_unlock_failed', 'vault_locked', 'vault_password_changed'} <= set(
        logged
    )


def test_five_failures_wait_five_minutes(client):  # noqa: F811
    me = setup(client)
    create_vault(client)
    client.post('/api/credentials/vault/lock')
    for _ in range(4):
        assert unlock(client, password='incorrecta-1234').status_code == 403
    assert unlock(client, password='incorrecta-1234').status_code == 429
    blocked = unlock(client, password=MASTER)  # even the right one waits
    assert blocked.status_code == 429 and state(client)['blocked_seconds'] > 240
    with SessionLocal() as db:
        db.execute(
            update(vault_keys).where(vault_keys.c.user_id == me).values(blocked_until=now() - timedelta(seconds=1))
        )
        db.commit()
    assert unlock(client, password=MASTER).status_code == 200
    assert actions().count('vault_unlock_failed') == 5


def test_auto_lock_after_minutes_without_use_and_logout(client, monkeypatch):  # noqa: F811
    setup(client)
    create_vault(client)
    assert client.put('/api/credentials/vault/settings', json={'auto_lock_minutes': 2}).status_code == 200
    client.post('/api/credentials/vault/lock')
    assert unlock(client, password=MASTER).json()['seconds_left'] == 120
    start = vault_session.clock()
    monkeypatch.setattr(vault_session, 'clock', lambda: start + 119)
    assert client.post('/api/credentials/vault/touch').json()['unlocked']  # activity restarts the count
    monkeypatch.setattr(vault_session, 'clock', lambda: start + 119 + 121)
    assert not state(client)['unlocked']
    assert client.get('/api/credentials/vault').status_code == 423
    monkeypatch.undo()
    assert unlock(client, password=MASTER).status_code == 200
    client.post('/api/auth/logout')
    login(client)
    assert not state(client)['unlocked']


# ---------------------------------------------------------------- authorized people


def test_members_get_a_temporary_code_and_their_own_master_password(client):  # noqa: F811
    setup(client)
    aux = add_user(client, 'aux')
    aux_id = aux['id'] if isinstance(aux, dict) else aux
    assert client.post('/api/credentials/vault/members', json={'user_id': aux_id}).status_code == 423  # locked
    create_vault(client)
    temporary = client.post('/api/credentials/vault/members', json={'user_id': aux_id}).json()['temporary_code']
    assert client.post('/api/credentials/vault/members', json={'user_id': aux_id}).status_code == 409
    assert [m['pending'] for m in client.get('/api/credentials/vault/members').json()] == [False, True]
    client.cookies.clear()
    login(client, 'aux')
    assert state(client)['member'] and not state(client)['can_setup']
    assert unlock(client, recovery_code=temporary).status_code == 403  # recovery is for administrators
    opened = unlock(client, password=temporary)
    assert opened.status_code == 200 and opened.json()['must_change']
    assert (
        client.post('/api/credentials/vault/password', json={'password': NEW_MASTER, 'confirm': NEW_MASTER}).status_code
        == 200
    )
    client.post('/api/credentials/vault/lock')
    assert unlock(client, password=NEW_MASTER).status_code == 200
    assert client.put('/api/credentials/vault/settings', json={'auto_lock_minutes': 9}).status_code == 403
    # The administrator removes the access: the open vault of that person locks at once.
    assert any(e.user_id == aux_id for e in vault_session._open.values())
    client.cookies.clear()
    login(client)
    unlock(client, password=MASTER)
    assert client.delete(f'/api/credentials/vault/members/{aux_id}').status_code == 200
    assert not any(e.user_id == aux_id for e in vault_session._open.values())
    client.cookies.clear()
    login(client, 'aux')
    assert not state(client)['member'] and unlock(client, password=NEW_MASTER).status_code == 403


def test_person_without_access_cannot_unlock(client):  # noqa: F811
    setup(client)
    create_vault(client)
    add_user(client, 'aux')
    client.cookies.clear()
    login(client, 'aux')
    assert not state(client)['member']
    assert unlock(client, password=MASTER).status_code == 403


# ---------------------------------------------------------------- migration of the previous keyring


def legacy_rows(old, cid):
    """A credential, its history and a file sealed with the previous DPAPI-style keyring."""
    ident, file_id = str(uuid4()), str(uuid4())
    envelope = old.seal(SECRET, cid, ident)
    v1 = dict(envelope)  # a version-1 envelope (sealed directly with the old key) must also move
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    aad = json.dumps(['contasuite-vault-v1', cid, ident, 'old-1'], separators=(',', ':')).encode()
    v1 = dict(
        v=1,
        key_version='old-1',
        algorithm='AES-256-GCM',
        nonce=base64.b64encode(nonce).decode(),
        ciphertext=base64.b64encode(AESGCM(old.keys['old-1']).encrypt(nonce, b'Anterior-Sint-0', aad)).decode(),
    )
    with SessionLocal() as db:
        db.execute(
            credentials.insert().values(
                id=ident,
                company_id=cid,
                service_id='sat_password',
                label='Acceso',
                envelope=envelope,
                revision=2,
                archived=False,
                created_at=now(),
                updated_at=now(),
                fingerprint=old.fingerprint(SECRET),
            )
        )
        db.execute(
            versions.insert().values(credential_id=ident, revision=1, envelope=v1, actor_id='x', created_at=now())
        )
        db.execute(
            versions.insert().values(credential_id=ident, revision=2, envelope=envelope, actor_id='x', created_at=now())
        )
        db.execute(
            files.insert().values(
                id=file_id,
                company_id=cid,
                credential_id=ident,
                file_kind='key',
                file_name='sintetico.key',
                envelope=old.seal_bytes(b'\x30synthetic-key', cid, 'file:' + file_id),
                sha256='0' * 64,
                size=15,
                actor_id='x',
                created_at=now(),
            )
        )
        db.commit()
    return ident, file_id


def test_setup_rewraps_the_previous_keyring_in_one_transaction(client, monkeypatch):  # noqa: F811
    cid = company(client, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(client)
    old = VaultCipher({'old-1': os.urandom(32)}, 'old-1')
    ident, file_id = legacy_rows(old, cid)
    # Without the previous keyring nothing is created nor changed.
    monkeypatch.delenv('CONTA_VAULT_KEYRING', raising=False)
    monkeypatch.setattr('app.credential_crypto.keyring_path', lambda *a: __import__('pathlib').Path('no-existe.dpapi'))
    refused = client.post('/api/credentials/vault/setup', json={'password': MASTER, 'confirm': MASTER})
    assert refused.status_code == 423 and not state(client)['configured']
    monkeypatch.setenv('CONTA_VAULT_KEYRING', json.dumps({'old-1': base64.b64encode(old.keys['old-1']).decode()}))
    monkeypatch.setenv('CONTA_VAULT_ACTIVE_KEY', 'old-1')
    made = client.post('/api/credentials/vault/setup', json={'password': MASTER, 'confirm': MASTER})
    assert made.status_code == 201 and made.json()['migrated'] == {'credentials': 1, 'versions': 2, 'files': 1}
    with SessionLocal() as db:
        dk = db.execute(select(vault_config.c.data_key_id)).scalar()
        envelopes = [db.execute(select(credentials.c.envelope)).scalar()]
        envelopes += list(db.scalars(select(versions.c.envelope)))
        envelopes += [db.execute(select(files.c.envelope).where(files.c.id == file_id)).scalar()]
        fingerprint = db.execute(select(credentials.c.fingerprint)).scalar()
    assert all(e['key_version'] == dk and e['v'] == 2 for e in envelopes)
    assert fingerprint != old.fingerprint(SECRET)
    # The old keyring is no longer needed: the secret opens with the master password alone.
    monkeypatch.delenv('CONTA_VAULT_KEYRING')
    client.post('/api/credentials/vault/lock')
    unlock(client, password=MASTER)
    assert client.post(f'/api/credentials/companies/{cid}/secrets/{ident}/reveal').json()['secret'] == SECRET
    cipher = vault_session.cipher(
        next(iter(vault_session._open))  # the only open session of this test
    )
    assert cipher.open(envelopes[1], cid, ident, authorize_recent=lambda: True) == 'Anterior-Sint-0'
    assert (
        cipher.open_bytes(envelopes[-1], cid, 'file:' + file_id, authorize_recent=lambda: True) == b'\x30synthetic-key'
    )
