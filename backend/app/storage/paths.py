import os
import re
import stat
from pathlib import Path, PurePosixPath
from .providers import StorageError

ALLOWED_EXTENSIONS = {'.pdf', '.xml', '.cer'}


def safe_key(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1000 or '\\' in value:
        raise StorageError('invalid_path')
    parts = value.split('/')
    if any(not p or p in {'.', '..'} or len(p) > 255 or p.endswith((' ', '.')) or
           re.search(r'[<>:"|?*\x00-\x1f]', p) or
           re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p, re.I) for p in parts):
        raise StorageError('invalid_path')
    return str(PurePosixPath(value))


def supported(key: str) -> bool:
    return PurePosixPath(key).suffix.lower() in ALLOWED_EXTENSIONS


def check_no_links(path: Path):
    # Covers NTFS junctions and reparse points on Python 3.11 as well as symlinks.
    for current in reversed((path, *path.parents)):
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise StorageError('linked_path')


def authorized_root(root: Path, allowed: tuple[Path, ...]) -> Path:
    try:
        root = Path(root)
        if not root.is_absolute() or not allowed:
            raise StorageError('unauthorized_root')
        # Reject UNC before lstat/resolve: even probing that path could contact a remote server.
        if os.name == 'nt' and (str(root).startswith('\\\\') or any(str(p).startswith('\\\\') for p in allowed)):
            raise StorageError('smb_not_configured')
        check_no_links(root)
        resolved = root.resolve(strict=True)
        authorized = []
        for candidate in allowed:
            if not candidate.is_absolute():
                raise StorageError('invalid_configuration')
            check_no_links(candidate)
            authorized.append(candidate.resolve(strict=True))
        if not resolved.is_dir() or not any(resolved.is_relative_to(a) for a in authorized):
            raise StorageError('unauthorized_root')
        # UNC access is reserved for a future explicitly enabled SMB adapter.
        if os.name == 'nt' and str(resolved).startswith('\\\\'):
            raise StorageError('smb_not_configured')
        return resolved
    except StorageError:
        raise
    except OSError:
        raise StorageError('root_unavailable') from None
