"""Authenticated encryption. Key providers and recent-auth adapters are server-owned."""
import os
import base64
import json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class VaultLocked(Exception):
    def __init__(self):super().__init__('Bóveda bloqueada o contenido no verificable.')

class VaultCipher:
    def __init__(self,keys,active):
        if active not in keys or any(len(k)!=32 for k in keys.values()):raise VaultLocked()
        self.keys,self.active=keys,active
    @classmethod
    def from_environment(cls):
        try:
            # Provision externally; never write these variables to .env or repository.
            raw=json.loads(os.environ.get('CONTA_VAULT_KEYRING','{}'))
            return cls({k:base64.b64decode(v,validate=True) for k,v in raw.items()},os.environ.get('CONTA_VAULT_ACTIVE_KEY',''))
        except Exception:raise VaultLocked() from None
    def seal(self,secret,company_id,record_id):
        try:
            nonce=os.urandom(12)
            aad=json.dumps(['contasuite-vault-v1',company_id,record_id,self.active],separators=(',',':')).encode()
            encrypted=AESGCM(self.keys[self.active]).encrypt(nonce,secret.encode(),aad)
            return dict(ciphertext=base64.b64encode(encrypted).decode(),nonce=base64.b64encode(nonce).decode(),key_version=self.active,algorithm='AES-256-GCM')
        except Exception:raise VaultLocked() from None
    def open(self,envelope,company_id,record_id,*,authorize_recent):
        # Callback must check trusted identity, permission and recent reauth. Never from HTTP body.
        if not authorize_recent():raise VaultLocked()
        try:
            version=envelope['key_version']
            if envelope['algorithm']!='AES-256-GCM':raise VaultLocked()
            aad=json.dumps(['contasuite-vault-v1',company_id,record_id,version],separators=(',',':')).encode()
            return AESGCM(self.keys[version]).decrypt(base64.b64decode(envelope['nonce'],validate=True),base64.b64decode(envelope['ciphertext'],validate=True),aad).decode()
        except Exception:raise VaultLocked() from None
