import json
import os
from dataclasses import dataclass
from pathlib import Path
from .providers import StorageError


@dataclass(frozen=True)
class StorageSettings:
    internal_root: Path
    legacy_root: Path
    allowed_roots: tuple[Path, ...] = ()
    max_file_bytes: int = 25 * 1024 * 1024
    max_scan_entries: int = 30000
    max_scan_seconds: float = 60
    smb_allowed_roots: tuple[Path, ...] = ()

    @classmethod
    def from_environment(cls, data: Path):
        try:
            roots = json.loads(os.getenv('CS_STORAGE_ALLOWED_ROOTS', '[]'))
            smb_roots = json.loads(os.getenv('CS_STORAGE_SMB_ALLOWED_ROOTS', '[]'))
            if not isinstance(smb_roots, list) or any(not isinstance(p, str) for p in smb_roots):
                raise ValueError
            from .smb import unc_root
            for value in smb_roots:
                unc_root(value)
            if not isinstance(roots, list) or any(not isinstance(p, str) or not Path(p).is_absolute() for p in roots):
                raise ValueError
            limit = int(os.getenv('CS_STORAGE_MAX_FILE_MB', '25'))
            if not 1 <= limit <= 100:
                raise ValueError
        except (ValueError, TypeError):
            raise StorageError('invalid_configuration') from None
        # Repository is fixed under private DATA; not under frontend/public.
        return cls(data / 'cs-storage', data / 'documents', tuple(Path(p) for p in roots), limit * 1024 * 1024,
                   smb_allowed_roots=tuple(Path(p) for p in smb_roots))
