"""Authenticated encryption. Key providers and recent-auth adapters are server-owned.

Plan v1.1 (Cambio 4): envelope encryption. Every secret or file gets its own random AES-256-GCM key (DEK); the DEK
is wrapped with the master key (KEK) of the keyring. The keyring never lives in the database: in production it is
a file protected with Windows DPAPI (`<DATA_DIR>/vault/keyring.dpapi`, created by scripts/vault_keyring.py, with a
separate offline backup); `CONTA_VAULT_KEYRING` in the process environment remains for tests and development only
and must never be written to `.env`. Envelopes of version 1 (sealed directly with the master key) still open.
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
    def from_environment(cls):
        """Keyring from the process environment (tests, development) or the DPAPI file (production)."""
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
