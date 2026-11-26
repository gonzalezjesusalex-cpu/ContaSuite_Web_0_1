"""Authenticated encryption. Key providers and recent-auth adapters are server-owned.

Envelope encryption: every secret or file gets its own random AES-256-GCM key (DEK), wrapped with a key-encryption
key. Since the renovación del gestor (fase 1, cs_0022) that key is the vault's data key, released only by a master
password or the recovery code and kept in server memory while the vault is unlocked (app/vault_session.py).

The previous keyring (Windows DPAPI file `<DATA_DIR>/vault/keyring.dpapi` from scripts/vault_keyring.py, or
`CONTA_VAULT_KEYRING` in the process environment for tests) is read only once: when the administrator creates the
vault, to re-wrap the existing envelopes (`rewrap`). Envelopes of version 1 still open and are re-sealed then.
"""

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEYRING_FILE = 'keyring.dpapi'


class VaultLocked(Exception):
    def __init__(self):
        super().__init__('Bóveda bloqueada o contenido no verificable.')


def _b64(data):
    return base64.b64encode(data).decode()


def _unb64(text):
    return base64.b64decode(text, validate=True)


# ---------------------------------------------------------------- Windows DPAPI (ctypes, no extra dependency)


def _dpapi(data, protect, machine=False, entropy=b'contasuite-vault'):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

    def blob(raw):
        buffer = ctypes.create_string_buffer(raw, len(raw))
        return Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    source, _keep1 = blob(data)
    extra, _keep2 = blob(entropy)
    out = Blob()
    flags = 0x1 | (0x4 if machine else 0)  # CRYPTPROTECT_UI_FORBIDDEN | CRYPTPROTECT_LOCAL_MACHINE
    call = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    args = (
        (ctypes.byref(source), 'ContaSuite', ctypes.byref(extra), None, None, flags, ctypes.byref(out))
        if protect
        else (ctypes.byref(source), None, ctypes.byref(extra), None, None, flags, ctypes.byref(out))
    )
    if not call(*args):
        raise VaultLocked()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def keyring_path(data_dir=None):
    # Same default as app.database.DATA, without importing it (it needs DATABASE_URL).
    root = Path(__file__).resolve().parents[2]
    base = Path(data_dir or os.environ.get('DATA_DIR') or root / 'data').resolve()
    return base / 'vault' / KEYRING_FILE


def write_keyring(keys, active, data_dir=None, machine=False):
    """Protect the keyring with DPAPI and write it; used by scripts/vault_keyring.py only."""
    payload = json.dumps({'active': active, 'keys': {k: _b64(v) for k, v in keys.items()}, 'machine': machine})
    path = keyring_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_dpapi(payload.encode(), True, machine))
    return path


def read_keyring(data_dir=None):
    path = keyring_path(data_dir)
    raw = path.read_bytes()
    try:
        data = json.loads(_dpapi(raw, False, False))
    except VaultLocked:
        data = json.loads(_dpapi(raw, False, True))
    return {k: _unb64(v) for k, v in data['keys'].items()}, data['active']


class VaultCipher:
    def __init__(self, keys, active):
        if active not in keys or any(len(k) != 32 for k in keys.values()):
            raise VaultLocked()
        self.keys, self.active = keys, active

    @classmethod
    def legacy_keyring(cls):
        """Previous keyring, only to re-wrap existing envelopes when the vault is created: the process environment
        (tests, development) or the DPAPI file. Never used to open secrets once the vault exists."""
        try:
            raw = os.environ.get('CONTA_VAULT_KEYRING')
            if raw:
                # Provision externally; never write these variables to .env or repository.
                keys = json.loads(raw)
                return cls({k: _unb64(v) for k, v in keys.items()}, os.environ.get('CONTA_VAULT_ACTIVE_KEY', ''))
            if os.name == 'nt' and keyring_path().is_file():
                return cls(*read_keyring())
        except Exception:  # noqa: BLE001 - vault errors must not reveal key material; reported as VaultLocked
            raise VaultLocked() from None
        raise VaultLocked()

    @staticmethod
    def _aad(company_id, record_id, version):
        return json.dumps(['contasuite-vault-v2', company_id, record_id, version], separators=(',', ':')).encode()

    def seal_bytes(self, data, company_id, record_id):
        """Envelope v2: a fresh data key encrypts the content; the master key wraps the data key."""
        try:
            dek, nonce, wrap_nonce = os.urandom(32), os.urandom(12), os.urandom(12)
            encrypted = AESGCM(dek).encrypt(nonce, data, self._aad(company_id, record_id, 'data'))
            wrapped = AESGCM(self.keys[self.active]).encrypt(
                wrap_nonce, dek, self._aad(company_id, record_id, 'key:' + self.active)
            )
            return dict(
                v=2,
                ciphertext=_b64(encrypted),
                nonce=_b64(nonce),
                wrapped_key=_b64(wrapped),
                wrap_nonce=_b64(wrap_nonce),
                key_version=self.active,
                algorithm='AES-256-GCM',
            )
        except Exception:  # noqa: BLE001 - vault errors must not reveal key material; reported as VaultLocked
            raise VaultLocked() from None

    def seal(self, secret, company_id, record_id):
        return self.seal_bytes(secret.encode(), company_id, record_id)

    def open_bytes(self, envelope, company_id, record_id, *, authorize_recent):
        # Callback must check trusted identity, permission and recent reauth. Never from HTTP body.
        if not authorize_recent():
            raise VaultLocked()
        try:
            version = envelope['key_version']
            if envelope['algorithm'] != 'AES-256-GCM':
                raise VaultLocked()
            if envelope.get('v') == 2:
                dek = AESGCM(self.keys[version]).decrypt(
                    _unb64(envelope['wrap_nonce']),
                    _unb64(envelope['wrapped_key']),
                    self._aad(company_id, record_id, 'key:' + version),
                )
                return AESGCM(dek).decrypt(
                    _unb64(envelope['nonce']),
                    _unb64(envelope['ciphertext']),
                    self._aad(company_id, record_id, 'data'),
                )
            aad = json.dumps(['contasuite-vault-v1', company_id, record_id, version], separators=(',', ':')).encode()
            return AESGCM(self.keys[version]).decrypt(_unb64(envelope['nonce']), _unb64(envelope['ciphertext']), aad)
        except Exception:  # noqa: BLE001 - vault errors must not reveal key material; reported as VaultLocked
            raise VaultLocked() from None

    def open(self, envelope, company_id, record_id, *, authorize_recent):
        return self.open_bytes(envelope, company_id, record_id, authorize_recent=authorize_recent).decode()

    def fingerprint(self, secret):
        """Keyed digest to find repeated passwords without decrypting them (never a plain hash)."""
        key = hmac.new(self.keys[self.active], b'contasuite-vault-fingerprint', hashlib.sha256).digest()
        return hmac.new(key, secret.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------- master password (renovación del gestor, fase 1)
#
# A random 256-bit data key encrypts every envelope (it wraps each per-secret key). The data key itself is stored only
# wrapped: once per authorized person with a key derived from their master password, and once with the recovery
# code. Derivation is Argon2id (cryptography >= 44); the parameters travel with each wrapped copy so they can be
# raised later without breaking existing copies.

KDF = {'alg': 'argon2id', 'iterations': 3, 'lanes': 4, 'memory_kib': 65536}
RECOVERY_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no 0/O, 1/I


def derive(password, salt, params):
    if params.get('alg') != 'argon2id':
        raise VaultLocked()
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

    return Argon2id(
        salt=salt,
        length=32,
        iterations=int(params['iterations']),
        lanes=int(params['lanes']),
        memory_cost=int(params['memory_kib']),
    ).derive(password.encode())


def _wrap_aad(row_id, data_key_id):
    return json.dumps(['contasuite-vault-master', row_id, data_key_id], separators=(',', ':')).encode()


def wrap_data_key(data_key, password, row_id, data_key_id, params=None):
    """A wrapped copy of the data key for one person (or the recovery code). Never stores the password."""
    params = dict(params or KDF)
    salt, nonce = os.urandom(16), os.urandom(12)
    wrapped = AESGCM(derive(password, salt, params)).encrypt(nonce, data_key, _wrap_aad(row_id, data_key_id))
    return dict(salt=_b64(salt), kdf=params, wrapped_key=_b64(wrapped), nonce=_b64(nonce))


def unwrap_data_key(row, password, data_key_id):
    """The data key, or VaultLocked when the password (or recovery code) is not the right one."""
    try:
        key = derive(password, _unb64(row['salt']), row['kdf'])
        return AESGCM(key).decrypt(_unb64(row['nonce']), _unb64(row['wrapped_key']), _wrap_aad(row['id'], data_key_id))
    except Exception:  # noqa: BLE001 - a wrong password must look the same as any other failure
        raise VaultLocked() from None


def recovery_code():
    """24 symbols in six groups (about 120 bits), printable and easy to type."""
    import secrets

    raw = ''.join(secrets.choice(RECOVERY_ALPHABET) for _ in range(24))
    return '-'.join(raw[i : i + 4] for i in range(0, 24, 4))


def normalize_recovery(code):
    """The same code typed with spaces, lowercase or without dashes."""
    raw = ''.join(c for c in (code or '').upper() if c in RECOVERY_ALPHABET)
    return '-'.join(raw[i : i + 4] for i in range(0, len(raw), 4))


def rewrap(envelope, old, new, company_id, record_id):
    """Move an envelope from the previous keyring to the vault's data key. Version 2 only re-wraps its per-secret
    key (the content is not re-encrypted); version 1 (sealed directly with an old key) is opened and sealed again."""
    if envelope.get('key_version') == new.active and envelope.get('v') == 2:
        return envelope
    if envelope.get('v') == 2:
        try:
            version = envelope['key_version']
            dek = AESGCM(old.keys[version]).decrypt(
                _unb64(envelope['wrap_nonce']),
                _unb64(envelope['wrapped_key']),
                old._aad(company_id, record_id, 'key:' + version),
            )
            wrap_nonce = os.urandom(12)
            wrapped = AESGCM(new.keys[new.active]).encrypt(
                wrap_nonce, dek, new._aad(company_id, record_id, 'key:' + new.active)
            )
        except Exception:  # noqa: BLE001
            raise VaultLocked() from None
        return {**envelope, 'wrapped_key': _b64(wrapped), 'wrap_nonce': _b64(wrap_nonce), 'key_version': new.active}
    data = old.open_bytes(envelope, company_id, record_id, authorize_recent=lambda: True)
    return new.seal_bytes(data, company_id, record_id)


COMMON = ('password', 'contrasena', 'contraseña', 'qwerty', 'abc123', '123456', '12345678', 'admin', 'sat123')


def strength(secret, rfc=''):
    """0 (very weak) to 4 (strong), checked locally; no external breach service is consulted."""
    if not secret:
        return 0
    lowered = secret.lower()
    classes = sum(
        [
            any(c.islower() for c in secret),
            any(c.isupper() for c in secret),
            any(c.isdigit() for c in secret),
            any(not c.isalnum() for c in secret),
        ]
    )
    score = 0
    if len(secret) >= 8:
        score += 1
    if len(secret) >= 12:
        score += 1
    if classes >= 3:
        score += 1
    if classes == 4 and len(secret) >= 10:
        score += 1
    if any(c in lowered for c in COMMON) or (rfc and rfc.lower()[:6] in lowered) or len(set(secret)) <= 3:
        score = min(score, 1)
    return score
