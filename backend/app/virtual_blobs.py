"""Internal copies of file contents for the virtual index, named by their SHA-256 (cs_0015).

The same content is stored once, however many companies or paths hold it. A blob is only written after its bytes hash to
the name it will carry, and a container of private keys is refused. The directory is created on the first write, never
at startup. Nothing here moves or changes an original file.
"""

import hashlib
import os
import re
from uuid import uuid4

from .database import DATA

MAX_BLOB = 25 * 1024 * 1024  # the agent does not hash (and so never copies) larger files
SHA = re.compile(r'^[0-9a-f]{64}$')


class BlobError(Exception):
    """A rejected copy; `code` is a stable reason, never an OS message."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def path_for(sha):
    if not SHA.fullmatch(sha or ''):
        raise BlobError('invalid_hash')
    return DATA / 'virtual_blobs' / sha[:2] / sha


def exists(sha):
    return bool(SHA.fullmatch(sha or '')) and path_for(sha).is_file()


def missing(hashes):
    """The hashes that have no stored copy yet."""
    return [h for h in dict.fromkeys(hashes) if not exists(h)]


def store(sha, data):
    """Store `data` under `sha` once it hashes to it. Returns True when a new blob was written."""
    target = path_for(sha)
    if len(data) > MAX_BLOB:
        raise BlobError('too_large')
    if hashlib.sha256(data).hexdigest() != sha:
        raise BlobError('hash_mismatch')
    if b'PRIVATE KEY' in data[:4096].upper():
        raise BlobError('protected_file')
    if target.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f'.{uuid4().hex}.part'
    try:
        with open(temporary, 'xb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, target)  # same name means same bytes, so a concurrent identical write is harmless
    finally:
        temporary.unlink(missing_ok=True)
    return True
