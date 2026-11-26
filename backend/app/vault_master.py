"""Renovación del gestor de contraseñas, fase 1: master password, unlock, lock and recovery code.

- The administrator creates the vault once: a random 256-bit data key, a wrapped copy for their master password
  (Argon2id, at least 12 characters) and another for a recovery code shown only once. Existing envelopes sealed with
  the previous DPAPI keyring are re-wrapped with the data key in the same transaction.
- Each authorized person has their own master password and their own wrapped copy; the administrator adds a person
  with a temporary code that must be replaced on first unlock, and removes them.
- The vault starts locked in every session, locks itself after `auto_lock_minutes` without use, on logout and with
  «Bloquear ahora». After five failed attempts the person waits five minutes. Every attempt goes to the log.
"""

import os
from datetime import timedelta
from uuid import uuid4

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from . import vault_session
from .credential_api import event, no_cache, ready, router
from .credential_crypto import (
    VaultCipher,
    VaultLocked,
    normalize_recovery,
    recovery_code,
    rewrap,
    unwrap_data_key,
    wrap_data_key,
)
from .credential_models import credentials, files, vault_config, vault_keys, versions
from .database import session
from .models import UserAccount, now
from .security import Principal, auth, utc

MIN_PASSWORD = 12
MAX_ATTEMPTS = 5
WAIT_MINUTES = 5
DEFAULT_MINUTES = 5


def personal(p):
    if p.bootstrap or not p.session_id:
        raise HTTPException(403, 'Se requiere una sesión personal.')


def config(db):
    return db.execute(select(vault_config).where(vault_config.c.id == 1)).mappings().first()


def own_key(db, user_id):
    return (
        db.execute(select(vault_keys).where(vault_keys.c.user_id == user_id, vault_keys.c.kind.in_(('user', 'invite'))))
        .mappings()
        .first()
    )


def recovery_key(db):
    return db.execute(select(vault_keys).where(vault_keys.c.kind == 'recovery')).mappings().first()


def new_key_row(db, kind, user_id, secret, data_key, data_key_id, actor):
    ident = str(uuid4())
    db.execute(
        vault_keys.insert().values(
            id=ident,
            kind=kind,
            user_id=user_id,
            failed_attempts=0,
            blocked_until=None,
            created_at=now(),
            created_by=actor,
            **wrap_data_key(data_key, secret, ident, data_key_id),
        )
    )
    return ident


def strong_enough(password):
    if len(password) < MIN_PASSWORD:
        raise HTTPException(422, f'La contraseña maestra debe tener al menos {MIN_PASSWORD} caracteres.')


# ---------------------------------------------------------------- state


@router.get('/vault/state')
def vault_state(response: Response, p: Principal = Depends(auth), db=Depends(session)):
    """What the screen needs before showing anything: never a company, credential or secret."""
    no_cache(response)
    ready(db)
    cfg = config(db)
    mine = own_key(db, p.subject) if cfg else None
    blocked = 0
    if mine and mine['blocked_until'] and utc(mine['blocked_until']) > now():
        blocked = int((utc(mine['blocked_until']) - now()).total_seconds()) + 1
    current = vault_session.state(p.session_id)
    return {
        'configured': bool(cfg),
        'member': bool(mine),
        'can_setup': not cfg and p.admin and not p.bootstrap,
        'unlocked': current['unlocked'],
        'seconds_left': current['seconds_left'],
        'must_change': current['must_change'],
        'auto_lock_minutes': cfg['auto_lock_minutes'] if cfg else DEFAULT_MINUTES,
        'blocked_seconds': blocked,
        'is_admin': p.admin,
    }


# ---------------------------------------------------------------- setup


class SetupIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: SecretStr = Field(max_length=256)
    confirm: SecretStr = Field(max_length=256)


def migrate_envelopes(db, new):
    """Re-wrap every envelope of the previous keyring with the data key, in the caller's transaction."""
    rows = {
        'credentials': list(db.execute(select(credentials.c.id, credentials.c.company_id, credentials.c.envelope))),
        'versions': list(
            db.execute(
                select(
                    versions.c.credential_id, versions.c.revision, credentials.c.company_id, versions.c.envelope
                ).join(credentials, credentials.c.id == versions.c.credential_id)
            )
        ),
        'files': list(db.execute(select(files.c.id, files.c.company_id, files.c.envelope))),
    }
    if not any(rows.values()):
        return {'credentials': 0, 'versions': 0, 'files': 0}
    try:
        old = VaultCipher.legacy_keyring()
    except VaultLocked:
        raise HTTPException(
            423,
            'Hay secretos guardados con la llave anterior y no se pudo leer en este equipo. '
            'Crea la bóveda en el equipo donde se configuró el gestor.',
        ) from None
    try:
        for ident, cid, envelope in rows['credentials']:
            moved = rewrap(envelope, old, new, cid, ident)
            secret = new.open(moved, cid, ident, authorize_recent=lambda: True)
            db.execute(
                update(credentials)
                .where(credentials.c.id == ident)
                .values(envelope=moved, fingerprint=new.fingerprint(secret))
            )
            del secret
        for ident, revision, cid, envelope in rows['versions']:
            db.execute(
                update(versions)
                .where(versions.c.credential_id == ident, versions.c.revision == revision)
                .values(envelope=rewrap(envelope, old, new, cid, ident))
            )
        for ident, cid, envelope in rows['files']:
            db.execute(
                update(files)
                .where(files.c.id == ident)
                .values(envelope=rewrap(envelope, old, new, cid, 'file:' + ident))
            )
    except VaultLocked:
        db.rollback()
        raise HTTPException(
            409, 'Un secreto guardado no se pudo abrir con la llave anterior; no se cambió nada.'
        ) from None
    return {k: len(v) for k, v in rows.items()}


@router.post('/vault/setup', status_code=201)
def vault_setup(payload: SetupIn, response: Response, p: Principal = Depends(auth), db=Depends(session)):
    """Create the vault (administrators, once). Returns the recovery code: the only time it is shown."""
    no_cache(response)
    ready(db)
    personal(p)
    p.require_admin()
    if config(db):
        raise HTTPException(409, 'La bóveda ya está configurada.')
    password = payload.password.get_secret_value()
    if password != payload.confirm.get_secret_value():
        raise HTTPException(422, 'Las contraseñas no coinciden.')
    strong_enough(password)
    data_key, data_key_id = os.urandom(32), str(uuid4())
    migrated = migrate_envelopes(db, VaultCipher({data_key_id: data_key}, data_key_id))
    code = recovery_code()
    try:
        db.execute(
            vault_config.insert().values(
                id=1,
                data_key_id=data_key_id,
                auto_lock_minutes=DEFAULT_MINUTES,
                created_at=now(),
                created_by=p.subject,
                migrated=migrated,
            )
        )
        new_key_row(db, 'user', p.subject, password, data_key, data_key_id, p.subject)
        new_key_row(db, 'recovery', None, code, data_key, data_key_id, p.subject)
        event(db, p, None, 'vault_setup', details={'migrated': migrated})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'La bóveda ya está configurada.') from None
    del password
    vault_session.unlock(p.session_id, p.subject, data_key_id, data_key, DEFAULT_MINUTES)
    return {'recovery_code': code, 'migrated': migrated, 'auto_lock_minutes': DEFAULT_MINUTES}


# ---------------------------------------------------------------- unlock and lock


class UnlockIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: SecretStr | None = Field(None, max_length=256)
    recovery_code: SecretStr | None = Field(None, max_length=64)


@router.post('/vault/unlock')
def vault_unlock(payload: UnlockIn, response: Response, p: Principal = Depends(auth), db=Depends(session)):
    no_cache(response)
    ready(db)
    personal(p)
    cfg = config(db)
    if not cfg:
        raise HTTPException(409, 'La bóveda todavía no está configurada.')
    mine = own_key(db, p.subject)
    if not mine:
        raise HTTPException(403, 'No tienes acceso a la bóveda. Pídelo a un administrador.')
    if mine['blocked_until'] and utc(mine['blocked_until']) > now():
        wait = int((utc(mine['blocked_until']) - now()).total_seconds()) + 1
        raise HTTPException(
            429, f'Demasiados intentos. Espera {wait // 60 + 1} minutos.', headers={'Retry-After': str(wait)}
        )
    if payload.recovery_code is not None:
        if not p.admin:
            raise HTTPException(403, 'Sólo un administrador puede usar el código de recuperación.')
        row, secret, via = recovery_key(db), normalize_recovery(payload.recovery_code.get_secret_value()), 'recovery'
    elif payload.password is not None:
        row, secret, via = (
            mine,
            payload.password.get_secret_value(),
            ('invite' if mine['kind'] == 'invite' else 'password'),
        )
    else:
        raise HTTPException(422, 'Escribe la contraseña maestra.')
    # The attempt is counted and committed before the (expensive) derivation.
    attempts = mine['failed_attempts'] + 1
    db.execute(update(vault_keys).where(vault_keys.c.id == mine['id']).values(failed_attempts=attempts))
    db.commit()
    try:
        data_key = unwrap_data_key(row, secret, cfg['data_key_id']) if row else None
    except VaultLocked:
        data_key = None
    del secret
    if data_key is None:
        values = {'failed_attempts': attempts}
        if attempts >= MAX_ATTEMPTS:
            values = {'failed_attempts': 0, 'blocked_until': now() + timedelta(minutes=WAIT_MINUTES)}
        db.execute(update(vault_keys).where(vault_keys.c.id == mine['id']).values(**values))
        event(db, p, None, 'vault_unlock_failed', details={'via': via, 'attempt': attempts})
        db.commit()
        if attempts >= MAX_ATTEMPTS:
            raise HTTPException(429, f'Demasiados intentos. Espera {WAIT_MINUTES} minutos.')
        raise HTTPException(
            403,
            'El código de recuperación no es correcto.'
            if via == 'recovery'
            else 'La contraseña maestra no es correcta.',
        )
    db.execute(update(vault_keys).where(vault_keys.c.id == mine['id']).values(failed_attempts=0, blocked_until=None))
    event(db, p, None, 'vault_unlocked', details={'via': via})
    db.commit()
    vault_session.unlock(p.session_id, p.subject, cfg['data_key_id'], data_key, cfg['auto_lock_minutes'], via)
    return vault_session.state(p.session_id)


@router.post('/vault/lock')
def vault_lock(response: Response, p: Principal = Depends(auth), db=Depends(session)):
    no_cache(response)
    ready(db)
    was = vault_session.unlocked(p.session_id)
    vault_session.lock(p.session_id)
    if was:
        event(db, p, None, 'vault_locked')
        db.commit()
    return {'unlocked': False}


@router.post('/vault/touch')
def vault_touch(response: Response, p: Principal = Depends(auth)):
    """Activity on the screen (scrolling, filtering) keeps the vault open; it never opens a locked one."""
    no_cache(response)
    vault_session.touch(p.session_id)
    return vault_session.state(p.session_id)


# ---------------------------------------------------------------- own master password and recovery code


def unlocked_cipher(db, p):
    try:
        return vault_session.cipher(p.session_id)
    except VaultLocked:
        raise HTTPException(423, 'La bóveda está bloqueada.') from None


def check_own(db, p, current):
    mine = own_key(db, p.subject)
    cfg = config(db)
    try:
        unwrap_data_key(mine, current, cfg['data_key_id'])
    except (VaultLocked, TypeError):
        event(db, p, None, 'vault_unlock_failed', details={'via': 'confirm'})
        db.commit()
        raise HTTPException(403, 'La contraseña maestra no es correcta.') from None


class PasswordIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current: SecretStr | None = Field(None, max_length=256)
    password: SecretStr = Field(max_length=256)
    confirm: SecretStr = Field(max_length=256)


@router.post('/vault/password')
def vault_password(payload: PasswordIn, response: Response, p: Principal = Depends(auth), db=Depends(session)):
    """Set a new own master password. After a recovery code or a temporary code the current one is not asked."""
    no_cache(response)
    ready(db)
    personal(p)
    cipher = unlocked_cipher(db, p)
    state = vault_session.state(p.session_id)
    password = payload.password.get_secret_value()
    if password != payload.confirm.get_secret_value():
        raise HTTPException(422, 'Las contraseñas no coinciden.')
    strong_enough(password)
    if not state['must_change']:
        check_own(db, p, payload.current.get_secret_value() if payload.current else '')
    cfg = config(db)
    db.execute(vault_keys.delete().where(vault_keys.c.user_id == p.subject, vault_keys.c.kind.in_(('user', 'invite'))))
    new_key_row(db, 'user', p.subject, password, cipher.keys[cfg['data_key_id']], cfg['data_key_id'], p.subject)
    event(db, p, None, 'vault_password_changed', details={'after': state.get('via')})
    db.commit()
    del password
    vault_session.changed_password(p.session_id)
    return vault_session.state(p.session_id)


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: SecretStr = Field(max_length=256)


@router.post('/vault/recovery')
def vault_recovery(payload: ConfirmIn, response: Response, p: Principal = Depends(auth), db=Depends(session)):
    """A new recovery code (administrators); the previous one stops working. Shown only once."""
    no_cache(response)
    ready(db)
    personal(p)
    p.require_admin()
    cipher = unlocked_cipher(db, p)
    check_own(db, p, payload.password.get_secret_value())
    cfg = config(db)
    code = recovery_code()
    db.execute(vault_keys.delete().where(vault_keys.c.kind == 'recovery'))
    new_key_row(db, 'recovery', None, code, cipher.keys[cfg['data_key_id']], cfg['data_key_id'], p.subject)
    event(db, p, None, 'vault_recovery_regenerated')
    db.commit()
    return {'recovery_code': code}


# ---------------------------------------------------------------- settings and members (administrators)


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    auto_lock_minutes: int = Field(ge=1, le=60)


@router.put('/vault/settings')
def vault_settings(payload: SettingsIn, response: Response, p: Principal = Depends(auth), db=Depends(session)):
    no_cache(response)
    ready(db)
    p.require_admin()
    if not config(db):
        raise HTTPException(409, 'La bóveda todavía no está configurada.')
    db.execute(update(vault_config).where(vault_config.c.id == 1).values(auto_lock_minutes=payload.auto_lock_minutes))
    event(db, p, None, 'vault_settings_changed', details=payload.model_dump())
    db.commit()
    vault_session.set_minutes(payload.auto_lock_minutes)
    return payload.model_dump()


@router.get('/vault/members')
def vault_members(response: Response, p: Principal = Depends(auth), db=Depends(session)):
    no_cache(response)
    ready(db)
    p.require_admin()
    rows = db.execute(
        select(vault_keys.c.user_id, vault_keys.c.kind, vault_keys.c.created_at, UserAccount.display_name)
        .join(UserAccount, UserAccount.id == vault_keys.c.user_id)
        .where(vault_keys.c.kind.in_(('user', 'invite')))
        .order_by(UserAccount.display_name)
    ).mappings()
    return [
        {'user_id': r['user_id'], 'name': r['display_name'], 'pending': r['kind'] == 'invite', 'since': r['created_at']}
        for r in rows
    ]


class MemberIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    user_id: str = Field(max_length=36)


@router.post('/vault/members', status_code=201)
def vault_add_member(payload: MemberIn, response: Response, p: Principal = Depends(auth), db=Depends(session)):
    """Give a person access: a temporary code (shown once) they replace with their own master password."""
    no_cache(response)
    ready(db)
    personal(p)
    p.require_admin()
    cipher = unlocked_cipher(db, p)
    user = db.get(UserAccount, payload.user_id)
    if not user or not user.enabled:
        raise HTTPException(422, 'Usuario no disponible.')
    if own_key(db, user.id):
        raise HTTPException(409, 'Esa persona ya tiene acceso a la bóveda.')
    cfg = config(db)
    code = recovery_code()
    new_key_row(db, 'invite', user.id, code, cipher.keys[cfg['data_key_id']], cfg['data_key_id'], p.subject)
    event(db, p, None, 'vault_member_added', details={'user_id': user.id})
    db.commit()
    return {'temporary_code': code}


@router.delete('/vault/members/{user_id}')
def vault_remove_member(user_id: str, response: Response, p: Principal = Depends(auth), db=Depends(session)):
    no_cache(response)
    ready(db)
    p.require_admin()
    if user_id == p.subject:
        raise HTTPException(422, 'No puedes quitarte el acceso a ti mismo.')
    removed = db.execute(
        vault_keys.delete().where(vault_keys.c.user_id == user_id, vault_keys.c.kind.in_(('user', 'invite')))
    ).rowcount
    if not removed:
        raise HTTPException(404, 'Esa persona no tiene acceso a la bóveda.')
    event(db, p, None, 'vault_member_removed', details={'user_id': user_id})
    db.commit()
    vault_session.lock_user(user_id)
    return {'removed': True}
