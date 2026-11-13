"""Verify a joint backup and restore exclusively into a newly created database."""

import argparse, hashlib, json, os, shutil, subprocess
from pathlib import Path


def verify(root):
    root = root.resolve()
    manifest = json.loads((root / 'sha256.json').read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or 'database.dump' not in manifest:
        raise ValueError('Incomplete backup manifest')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p != root / 'sha256.json'}
    if actual != set(manifest):
        raise ValueError('Backup file inventory differs')
    for name, digest in manifest.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or path.is_symlink() or not path.is_file():
            raise ValueError('Unsafe backup path')
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(block)
        if h.hexdigest() != digest:
            raise ValueError('Backup integrity mismatch: ' + name)
    return manifest


def restore(backup, pg_bin, database, data):
    import psycopg
    from psycopg import sql

    verify(backup)
    if not database.startswith('contasuite_restore_') or len(database) > 63:
        raise ValueError('Use a NEW contasuite_restore_ database name')
    if not data.is_absolute() or data.exists():
        raise ValueError('New absolute data directory required')
    if not os.environ.get('PGHOST') or not os.environ.get('PGUSER'):
        raise ValueError('Explicit PostgreSQL connection required')
    with psycopg.connect(dbname='postgres', autocommit=True) as connection:
        if connection.execute('SELECT 1 FROM pg_database WHERE datname=%s', (database,)).fetchone():
            raise ValueError('Destination database already exists; no overwrite')
        connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    result = subprocess.run(
        [
            str(pg_bin / 'pg_restore.exe'),
            '--exit-on-error',
            '--no-owner',
            '--dbname',
            database,
            str(backup / 'database.dump'),
        ],
        capture_output=True,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    if result.returncode:
        raise RuntimeError('Restore failed; new database retained for diagnosis')
    shutil.copytree(backup / 'data', data)
    manifest = verify(backup)
    for name, digest in manifest.items():
        if name.startswith('data/') and hashlib.sha256((data / name[5:]).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Restored file verification failed')
    return {
        'database': database,
        'files_verified': sum(n.startswith('data/') for n in manifest),
        'existing_databases_modified': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--pg-bin', type=Path)
    parser.add_argument('--database')
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    if args.verify_only:
        print(json.dumps({'verified_files': len(verify(args.backup))}))
        return
    if not all((args.pg_bin, args.database, args.data_dir)):
        parser.error('Explicit new database, data directory and pg-bin required')
    print(json.dumps(restore(args.backup, args.pg_bin, args.database, args.data_dir)))


if __name__ == '__main__':
    main()
