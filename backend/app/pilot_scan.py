"""Bounded local pilot preview. Never opens unsupported/secret files or follows links."""
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from .storage.local import LocalFolderProvider
from .storage.paths import safe_key, check_no_links
from .storage.providers import StorageError

SECRET_PATTERNS = ('*password*', '*contrase*', '*credencial*', '*secret*', '*.key', '*.pfx', '*.p12',
                   '*.pem', '*.env*', '*respaldo*', '*backup*', '*.bak', '*.sql', '*.dump',
                   '*.zip', '*.7z', '*.rar', '*token*', '*llave*', '.git', 'node_modules')


def configured_limits():
    try:
        files=int(os.getenv('CS_PILOT_MAX_FILES','200'))
        megabytes=int(os.getenv('CS_PILOT_MAX_MB','100'))
        seconds=int(os.getenv('CS_PILOT_MAX_SECONDS','90'))
        if not 1<=files<=1000 or not 1<=megabytes<=500 or not 1<=seconds<=300:raise ValueError
        return {'max_files':files,'max_bytes':megabytes*1024*1024,'max_seconds':seconds}
    except ValueError:raise StorageError('invalid_configuration') from None


def roots_from_environment():
    try:
        values = json.loads(os.environ.get('CS_PILOT_ROOTS', '[]'))
        if not isinstance(values, list) or len(values) not in (0, 2):
            raise ValueError
        # Reject UNC/device/relative paths before any filesystem probe.
        paths = [Path(v) for v in values if isinstance(v, str)]
        if len(paths) != len(values) or any(not p.is_absolute() or str(p).startswith(('\\\\', '//')) for p in paths):
            raise ValueError
        if len(set(str(p).casefold() for p in paths)) != len(paths):
            raise ValueError
        if os.name == 'nt':
            import ctypes
            # Refuse mapped network drives before lstat/scandir can contact SMB.
            if any(ctypes.windll.kernel32.GetDriveTypeW(str(p.anchor)) != 3 for p in paths):
                raise ValueError
        return paths
    except (ValueError, TypeError):
        raise StorageError('invalid_configuration') from None


def extract(content, name):
    """Uses the existing sandboxed classifier process; no raw text is returned."""
    payload = json.dumps({'content': base64.b64encode(content).decode(), 'name': name})
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
    try:
        bootstrap = 'import sys,runpy;sys.path.insert(0,sys.argv[1]);runpy.run_module("app.pilot_extract",run_name="__main__")'
        proc = subprocess.run([sys.executable, '-B', '-c', bootstrap, str(Path(__file__).resolve().parents[1])], input=payload,
                              capture_output=True, text=True, timeout=8, env=env,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if proc.returncode:
            raise ValueError
        return json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, ValueError):
        return {'type': 'unknown', 'period': None, 'evidence': {'reason': 'extraction_failed', 'complete': False, 'rfcs': []}, 'identities': []}


def scan(paths, *, max_files=200, max_bytes=100*1024*1024, max_seconds=90, exclusions=()):
    start = time.monotonic()
    all_rows, folders = [], []
    total = 0
    providers = [LocalFolderProvider(p, tuple(paths), exclusions=SECRET_PATTERNS+tuple(exclusions),
                 max_entries=5000, max_file_bytes=25*1024*1024, max_seconds=max_seconds) for p in paths]
    if len(providers) != 2 or any(a.root.is_relative_to(b.root) or b.root.is_relative_to(a.root)
                                 for a, b in [(providers[0], providers[1])]):
        raise StorageError('invalid_configuration')
    for index, provider in enumerate(providers):
        folder = {'id': str(index), 'name': provider.root.name, 'path': str(provider.root), 'files': 0,
                  'bytes': 0, 'types': {}, 'subfolders': [], 'issues': [], 'excluded': 0}
        # Enumerate metadata (including unsupported entries) without opening excluded bytes.
        pending, visited = [provider.root], 0
        while pending:
            directory = pending.pop()
            try:
                check_no_links(directory)
                with os.scandir(directory) as entries:
                    for entry in entries:
                        visited += 1
                        if visited > 5000 or time.monotonic()-start > max_seconds:
                            raise StorageError('scan_limit')
                        key = Path(entry.path).relative_to(provider.root).as_posix()
                        if provider._excluded(key):
                            folder['excluded'] += 1
                            continue
                        try:
                            safe_key(key)
                            check_no_links(Path(entry.path))
                            if entry.is_dir(follow_symlinks=False):
                                folder['subfolders'].append(key)
                                pending.append(Path(entry.path))
                            elif entry.is_file(follow_symlinks=False):
                                size = entry.stat(follow_symlinks=False).st_size
                                folder['files'] += 1
                                folder['bytes'] += size
                                suffix = Path(key).suffix.lower()
                                folder['types'][suffix or '(sin extensión)'] = folder['types'].get(suffix or '(sin extensión)', 0)+1
                                if suffix not in {'.xml', '.pdf', '.cer'}:
                                    folder['issues'].append({'key': key, 'code': 'unsupported_format'})
                                    continue
                                if len(all_rows) >= max_files or total+size > max_bytes:
                                    raise StorageError('scan_limit')
                                with provider.open_read(key) as stream:
                                    content = stream.read(provider.max_file_bytes+1)
                                total += len(content)
                                result = extract(content, Path(key).name)
                                all_rows.append({'folder': str(index), 'key': key, 'size': len(content),
                                    'sha256': hashlib.sha256(content).hexdigest(), 'result': result,
                                    'type': result['type'], 'links': [], 'include': True,
                                    'error': None if result['evidence'].get('readable') else result['evidence'].get('reason', 'unreadable_content')})
                        except StorageError as exc:
                            if exc.code == 'scan_limit': raise
                            folder['issues'].append({'key': key, 'code': exc.code})
                        except OSError:
                            folder['issues'].append({'key': key, 'code': 'read_error'})
            except OSError:
                folder['issues'].append({'key': directory.relative_to(provider.root).as_posix(), 'code': 'access_denied'})
        folder['subfolders'].sort()
        folder['issues'].sort(key=lambda x:(x['key'],x['code']))
        folders.append(folder)
    if time.monotonic()-start > max_seconds: raise StorageError('scan_limit')
    by_uuid, by_hash = defaultdict(list), defaultdict(list)
    for r in all_rows:
        by_hash[r['sha256']].append(r)
        uuid = r['result']['evidence'].get('cfdi_uuid')
        if uuid: by_uuid[uuid].append(r)
    for r in all_rows:
        uuid = r['result']['evidence'].get('cfdi_uuid')
        r['duplicate'] = len(by_hash[r['sha256']]) > 1
        r['conflict'] = (r['result']['evidence'].get('uuid_status') == 'contradictory' or
                         bool(uuid and len({x['sha256'] for x in by_uuid[uuid]}) > 1))
    all_rows.sort(key=lambda r: (r['folder'], r['key'].casefold()))
    fingerprint = hashlib.sha256(json.dumps({'folders': folders, 'files': [
        {k:r[k] for k in ('folder','key','size','sha256')} for r in all_rows]}, sort_keys=True).encode()).hexdigest()
    return {'folders': folders, 'documents': all_rows, 'fingerprint': fingerprint}
