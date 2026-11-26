"""Unlocked vaults, in server memory only (renovación del gestor, fase 1).

The data key lives here while a session has the vault unlocked: never on disk, in the database, cookies, the
browser or logs. Each entry belongs to one login session and expires after `minutes` without use; logging out,
revoking the session or «Bloquear ahora» drops it. The API runs as a single process (scripts/service_runtime.py,
workers=1), so one dictionary is the whole state; a restart locks every vault.
"""

import threading
import time
from dataclasses import dataclass

from .credential_crypto import VaultCipher, VaultLocked


@dataclass
class _Entry:
    user_id: str
    data_key_id: str
    data_key: bytearray
    minutes: int
    last_used: float
    via: str  # 'password', 'recovery' or 'invite' (the last two must set a new master password)


_lock = threading.Lock()
_open: dict[str, _Entry] = {}
# Extension tickets (60 s): the hash of the ticket -> the session that issued it, whose vault must still be open.
_tickets: dict[str, tuple[str, float]] = {}
clock = time.monotonic


def _wipe(entry):
    for i in range(len(entry.data_key)):
        entry.data_key[i] = 0


def _alive(session_id):
    entry = _open.get(session_id)
    if entry and clock() - entry.last_used > entry.minutes * 60:
        _wipe(_open.pop(session_id))
        return None
    return entry


def unlock(session_id, user_id, data_key_id, data_key, minutes, via='password'):
    with _lock:
        if session_id in _open:
            _wipe(_open.pop(session_id))
        _open[session_id] = _Entry(user_id, data_key_id, bytearray(data_key), int(minutes), clock(), via)


def cipher(session_id, touch=True):
    """The cipher of an unlocked session, or VaultLocked. Using it counts as activity."""
    with _lock:
        entry = _alive(session_id) if session_id else None
        if not entry:
            raise VaultLocked()
        if touch:
            entry.last_used = clock()
        return VaultCipher({entry.data_key_id: bytes(entry.data_key)}, entry.data_key_id)


def state(session_id):
    with _lock:
        entry = _alive(session_id) if session_id else None
        if not entry:
            return {'unlocked': False, 'seconds_left': 0, 'must_change': False}
        left = max(0, int(entry.minutes * 60 - (clock() - entry.last_used)))
        return {'unlocked': True, 'seconds_left': left, 'must_change': entry.via != 'password', 'via': entry.via}


def touch(session_id):
    with _lock:
        entry = _alive(session_id) if session_id else None
        if entry:
            entry.last_used = clock()
        return bool(entry)


def unlocked(session_id):
    return state(session_id)['unlocked']


def changed_password(session_id):
    with _lock:
        entry = _alive(session_id)
        if entry:
            entry.via = 'password'


def set_minutes(minutes):
    with _lock:
        for entry in _open.values():
            entry.minutes = int(minutes)


def lock(session_id):
    with _lock:
        if session_id in _open:
            _wipe(_open.pop(session_id))


def lock_user(user_id):
    with _lock:
        for sid in [s for s, e in _open.items() if e.user_id == user_id]:
            _wipe(_open.pop(sid))


def lock_all():
    with _lock:
        for sid in list(_open):
            _wipe(_open.pop(sid))
        _tickets.clear()


def remember_ticket(token_hash, session_id, seconds):
    with _lock:
        now = clock()
        for k in [k for k, (_, until) in _tickets.items() if until < now]:
            del _tickets[k]
        _tickets[token_hash] = (session_id, now + seconds)


def ticket_session(token_hash):
    with _lock:
        found = _tickets.pop(token_hash, None)
        return found[0] if found and found[1] >= clock() else None
