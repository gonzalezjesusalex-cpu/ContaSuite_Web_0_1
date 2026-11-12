"""Read-only UNC provider using the Windows process identity; no stored credentials."""
import os
from pathlib import Path, PureWindowsPath
from .local import LocalFolderProvider
from .paths import check_no_links, safe_key
from .providers import Availability, StorageError


def unc_root(value):
    """Validate syntax before any filesystem/network call."""
    value = str(value).replace('/', '\\')
    path = PureWindowsPath(value)
    if (not value.startswith('\\\\') or value.startswith(('\\\\?\\', '\\\\.\\')) or
            not path.is_absolute() or not path.drive.startswith('\\\\')):
        raise StorageError('invalid_path')
    server, share = path.drive[2:].split('\\', 1)
    safe_key(server)
    safe_key(share)
    if len(path.parts) > 1:
        safe_key('/'.join(path.parts[1:]))
    return path


def windows_root(configuration):
    server, share = configuration.get('server', ''), configuration.get('share', '')
    if not server or not share:
        raise StorageError('smb_not_configured')
    subdirectory = configuration.get('subdirectory', '').replace('\\', '/')
    if subdirectory:
        safe_key(subdirectory)
    return unc_root('\\\\' + server + '\\' + share + ('\\' + subdirectory if subdirectory else ''))


class WindowsSMBProvider(LocalFolderProvider):
    allow_unc_handle = True

    def __init__(self, root=None, allowed_roots=(), **kwargs):
        self.configured = root is not None
        if self.configured:
            super().__init__(Path(root), allowed_roots, **kwargs)

    def _authorize_root(self, root, allowed_roots):
        requested = unc_root(root)
        allowed = tuple(unc_root(p) for p in allowed_roots)
        if not any(requested.is_relative_to(candidate) for candidate in allowed):
            raise StorageError('unauthorized_root')
        if os.name != 'nt':
            raise StorageError('smb_requires_windows')
        try:
            path = Path(requested)
            check_no_links(path)
            resolved = path.resolve(strict=True)
            if not resolved.is_dir() or not any(PureWindowsPath(resolved).is_relative_to(p) for p in allowed):
                raise StorageError('unauthorized_root')
            return resolved
        except PermissionError:
            raise StorageError('access_denied') from None
        except OSError:
            raise StorageError('root_unavailable') from None

    def availability(self):
        return super().availability() if self.configured else Availability('pending_configuration', 'smb_not_configured')

    def enumerate(self):
        if not self.configured:
            raise StorageError('smb_not_configured')
        return super().enumerate()

    def metadata(self, key):
        if not self.configured:
            raise StorageError('smb_not_configured')
        return super().metadata(key)

    def open_read(self, key):
        if not self.configured:
            raise StorageError('smb_not_configured')
        return super().open_read(key)
