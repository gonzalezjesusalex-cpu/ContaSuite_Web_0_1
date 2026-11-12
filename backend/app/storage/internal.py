import hashlib
import os
import re
from pathlib import Path
from uuid import uuid4
from defusedxml import ElementTree
from .local import LocalFolderProvider
from .paths import check_no_links, safe_key, supported
from .providers import Availability, StorageError, StoredFile

OBJECT_KEY = re.compile(r'^objects/[a-f0-9]{32}\.(pdf|xml|cer)$')


def validate_payload(stream, name, *, allow_public_cer=False):
    """PDF/XML validation; public CER validation is explicit and never accepts private-key containers."""
    safe_key(name)
    certificate = allow_public_cer and Path(name).suffix.lower() == '.cer'
    if '/' in name or (not supported(name) and not certificate):
        raise StorageError('unsupported_format')
    stream.seek(0)
    prefix = stream.read(4096)
    if b'PRIVATE KEY' in prefix.upper():
        raise StorageError('protected_file')
    if certificate:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding
        try:
            stream.seek(0)
            data = stream.read()
            if data.lstrip().startswith(b'-----BEGIN CERTIFICATE-----'):
                cert = x509.load_pem_x509_certificate(data)
                if cert.public_bytes(Encoding.PEM).strip() != data.replace(b'\r\n', b'\n').strip():
                    raise ValueError
            else:
                cert = x509.load_der_x509_certificate(data)
                if cert.public_bytes(Encoding.DER) != data:
                    raise ValueError
        except Exception:
            raise StorageError('invalid_public_certificate') from None
        media_type = 'application/pkix-cert'
    elif Path(name).suffix.lower() == '.pdf':
        if not prefix.startswith(b'%PDF-'):
            raise StorageError('invalid_format')
        media_type = 'application/pdf'
    else:
        try:
            stream.seek(0)
            # No entities, DTD or external resources. Parsing/classification is not inferred from names.
            ElementTree.parse(stream, forbid_dtd=True, forbid_entities=True, forbid_external=True)
        except Exception:
            raise StorageError('invalid_format') from None
        media_type = 'application/xml'
    stream.seek(0)
    return media_type


class InternalStorageProvider:
    """Writes only generated names to a private repository. No caller-supplied absolute destinations."""
    def __init__(self, root: Path, *, max_file_bytes=25 * 1024 * 1024):
        self.root = Path(root).absolute()
        self.max_file_bytes = max_file_bytes

    def _prepare(self):
        try:
            # Validate all existing ancestors before creating anything.
            current = self.root
            while True:
                try:
                    current.lstat()
                    break
                except FileNotFoundError:
                    current = current.parent
            check_no_links(current)
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            check_no_links(self.root)
            for name in ('.staging', 'objects'):
                target = self.root / name
                if target.exists() or target.is_symlink():
                    check_no_links(target)
                target.mkdir(exist_ok=True, mode=0o700)
                check_no_links(target)
        except StorageError:
            raise
        except OSError:
            raise StorageError('repository_unavailable') from None

    def _reader(self):
        return LocalFolderProvider(self.root, (self.root,), max_file_bytes=self.max_file_bytes,
                                   exclusions=('.staging',))

    def availability(self):
        try:
            return self._reader().availability()
        except StorageError as exc:
            return Availability('unavailable', exc.code)

    def enumerate(self):
        yield from self._reader().enumerate()

    def metadata(self, key):
        if not OBJECT_KEY.fullmatch(key):
            raise StorageError('invalid_path')
        return self._reader().metadata(key)

    def open_read(self, key):
        if not OBJECT_KEY.fullmatch(key):
            raise StorageError('invalid_path')
        return self._reader().open_read(key)

    def put(self, stream, name):
        safe_key(name)
        if '/' in name or not supported(name):
            raise StorageError('unsupported_format')
        self._prepare()
        token = uuid4().hex
        temporary = self.root / '.staging' / token
        key = 'objects/' + token + Path(name).suffix.lower()
        target = self.root / key
        published = False
        staged = False
        try:
            size = 0
            digest = hashlib.sha256()
            with temporary.open('xb+') as out:
                staged = True
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.max_file_bytes:
                        raise StorageError('file_too_large')
                    digest.update(chunk)
                    out.write(chunk)
                if not size:
                    raise StorageError('empty_file')
                media_type = validate_payload(out, name, allow_public_cer=True)
                out.flush()
                os.fsync(out.fileno())
            # Atomic publication without replacing any existing object (NTFS and POSIX).
            check_no_links(target.parent)
            os.link(temporary, target)
            published = True
            with self.open_read(key) as reader:
                actual = hashlib.file_digest(reader, 'sha256').hexdigest()
            if actual != digest.hexdigest():
                raise StorageError('integrity_error')
            return StoredFile(key, size, actual, media_type)
        except StorageError:
            if published:
                self.discard(key)
            raise
        except OSError:
            if published:
                self.discard(key)
            raise StorageError('write_error') from None
        finally:
            try:
                if staged:
                    temporary.unlink(missing_ok=True)
            except OSError:
                raise StorageError('cleanup_failed') from None

    def discard(self, key):
        """Only for rollback of an object created by this repository; not a document delete API."""
        if not OBJECT_KEY.fullmatch(key):
            raise StorageError('invalid_path')
        try:
            path = self.root / safe_key(key)
            check_no_links(path.parent)
            if path.is_symlink():
                raise StorageError('linked_path')
            path.unlink(missing_ok=True)
        except StorageError:
            raise
        except OSError:
            raise StorageError('rollback_failed') from None
