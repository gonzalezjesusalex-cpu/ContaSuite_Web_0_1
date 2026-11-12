import fnmatch
import os
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from .paths import authorized_root, check_no_links, safe_key, supported
from .providers import Availability, FileMetadata, ScanIssue, StorageError


def os_error(exc):
    return 'missing' if isinstance(exc, FileNotFoundError) else 'access_denied' if isinstance(exc, PermissionError) else 'read_error'


class LocalFolderProvider:
    """Read-only, bounded traversal. Roots come from server configuration, never from document requests."""
    def __init__(self, root: Path, allowed_roots: tuple[Path, ...], *, exclusions=(), max_entries=30000,
                 max_seconds=60, max_file_bytes=25 * 1024 * 1024, allow_legacy_public_cer=False):
        self.root = self._authorize_root(root, allowed_roots)
        self.exclusions = tuple(exclusions)
        self.max_entries = max_entries
        self.max_seconds = max_seconds
        self.max_file_bytes = max_file_bytes
        self.allow_legacy_public_cer = allow_legacy_public_cer

    allow_unc_handle = False

    def _authorize_root(self, root, allowed_roots):
        return authorized_root(root, allowed_roots)

    def _supported(self, key):
        return supported(key) or (self.allow_legacy_public_cer and Path(key).suffix.lower() == '.cer')

    def _excluded(self, key):
        parts = key.split('/')
        return any(fnmatch.fnmatchcase('/'.join(parts[:n + 1]).casefold(), pattern.casefold()) or
                   fnmatch.fnmatchcase(part.casefold(), pattern.casefold())
                   for n, part in enumerate(parts) for pattern in self.exclusions)

    def _path(self, key):
        safe_key(key)
        if self._excluded(key):
            raise StorageError('excluded_path')
        if not self._supported(key):
            raise StorageError('unsupported_format')
        path = self.root / key
        check_no_links(path)
        if not path.resolve(strict=True).is_relative_to(self.root):
            raise StorageError('invalid_path')
        if not stat.S_ISREG(path.stat().st_mode):
            raise StorageError('not_a_file')
        return path

    def availability(self):
        try:
            check_no_links(self.root)
            with os.scandir(self.root):
                pass
            return Availability('available')
        except StorageError as exc:
            return Availability('unavailable', exc.code)
        except OSError as exc:
            return Availability('unavailable', os_error(exc))

    def metadata(self, key):
        try:
            path = self._path(key)
            info = path.stat()
            return FileMetadata(key, info.st_size, info.st_mtime_ns)
        except StorageError:
            raise
        except OSError as exc:
            raise StorageError(os_error(exc)) from None

    def enumerate(self):
        started = time.monotonic()
        pending = [self.root]
        visited = 0
        while pending:
            directory = pending.pop()
            key = directory.relative_to(self.root).as_posix()
            try:
                check_no_links(directory)
                if not directory.resolve(strict=True).is_relative_to(self.root):
                    raise StorageError('invalid_path')
                with os.scandir(directory) as entries:
                    for entry in entries:
                        visited += 1
                        if visited > self.max_entries or time.monotonic() - started > self.max_seconds:
                            yield ScanIssue('', 'scan_limit')
                            return
                        path = Path(entry.path)
                        rel = path.relative_to(self.root).as_posix()
                        if self._excluded(rel):
                            continue
                        try:
                            safe_key(rel)
                            info = entry.stat(follow_symlinks=False)
                            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                                yield ScanIssue(rel, 'linked_path')
                            elif stat.S_ISDIR(info.st_mode):
                                pending.append(path)
                            elif stat.S_ISREG(info.st_mode) and self._supported(rel):
                                yield self.metadata(rel)
                        except StorageError as exc:
                            yield ScanIssue(rel, exc.code)
                        except OSError as exc:
                            yield ScanIssue(rel, os_error(exc))
            except StorageError as exc:
                yield ScanIssue(key, exc.code)
            except OSError as exc:
                yield ScanIssue(key, os_error(exc))

    @contextmanager
    def open_read(self, key):
        """Open without following links. Validate the open handle, not only a pre-open path."""
        handle = None
        directory_fds = []
        try:
            path = self._path(key)
            flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
            if os.name == 'nt':
                fd = os.open(path, flags)
            else:
                directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                directory_fds.append(directory)
                for part in Path(key).parts[:-1]:
                    directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    directory_fds.append(directory)
                fd = os.open(Path(key).name, flags, dir_fd=directory)
            handle = os.fdopen(fd, 'rb')
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_size > self.max_file_bytes:
                raise StorageError('file_too_large' if opened.st_size > self.max_file_bytes else 'not_a_file')
            if os.name == 'nt':
                self._validate_windows_handle(handle)
            checked = self._path(key).stat()
            if (opened.st_dev, opened.st_ino) != (checked.st_dev, checked.st_ino):
                raise StorageError('file_changed')
            yield handle
            final = os.fstat(handle.fileno())
            if (opened.st_size, opened.st_mtime_ns) != (final.st_size, final.st_mtime_ns):
                raise StorageError('file_changed')
        except StorageError:
            raise
        except OSError as exc:
            raise StorageError(os_error(exc)) from None
        finally:
            if handle:
                handle.close()
            for descriptor in reversed(directory_fds):
                os.close(descriptor)

    def _validate_windows_handle(self, handle):
        import ctypes
        import msvcrt
        from ctypes import wintypes
        final_path = ctypes.windll.kernel32.GetFinalPathNameByHandleW
        final_path.argtypes = (wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD)
        final_path.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        count = final_path(msvcrt.get_osfhandle(handle.fileno()), buffer, len(buffer), 0)
        if not count or count >= len(buffer):
            raise StorageError('handle_validation_failed')
        value = buffer.value
        if value.startswith('\\\\?\\UNC\\'):
            if not self.allow_unc_handle:
                raise StorageError('smb_not_configured')
            value = '\\\\' + value[8:]
        if value.startswith('\\\\?\\'):
            value = value[4:]
        if not Path(value).is_relative_to(self.root):
            raise StorageError('invalid_path')
