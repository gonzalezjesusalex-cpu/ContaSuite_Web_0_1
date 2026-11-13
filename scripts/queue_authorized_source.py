"""Explicit operator authorization of ONE real local source, with backup before queueing."""

import argparse, hashlib, json, os, shutil, sys, getpass, subprocess
from pathlib import Path
from local_setup import marker, validate_roots, write_secret, start_postgres
from local_runtime import stop, start, alive
from secure_config import load


def prepare(root, folder):
    values = marker(root)
    folder = Path(validate_roots([str(folder)], forbidden=(root,))[0])
    # Validate paths/junctions before touching configuration or the application.
    from app.storage.local import LocalFolderProvider
    from app.pilot_scan import SECRET_PATTERNS

    LocalFolderProvider(folder, (folder,), exclusions=SECRET_PATTERNS)
    stop(root)
    start_postgres(root)
    try:
        config = load(root / 'private/service.json')
        from sqlalchemy.engine import make_url

        url = make_url(config['DATABASE_URL'])
        if url.database != values['database'] or url.host != '127.0.0.1' or url.port != values['pg_port']:
            raise ValueError('La conexión no pertenece a esta instalación.')
        env = os.environ.copy()
        env.update(PGHOST=url.host, PGPORT=str(url.port), PGUSER=url.username, PGPASSWORD=url.password)
        before = set((root / 'backups').glob('contasuite-*')) if (root / 'backups').exists() else set()
        command = [
            root / 'runtime/python.exe',
            '-B',
            root / 'app/scripts/backup_postgres.py',
            '--pg-bin',
            root / 'postgresql/bin',
            '--database',
            url.database,
            '--destination',
            root / 'backups',
            '--data-dir',
            root / 'data',
            '--writers-stopped',
        ]
        if alive(root):
            raise RuntimeError('Los escritores no están detenidos.')
        result = subprocess.run(
            [str(v) for v in command],
            env=env,
            capture_output=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            timeout=180,
        )
        if result.returncode:
            raise RuntimeError('Falló el respaldo previo; no se autorizó una nueva importación.')
        backup = (set((root / 'backups').glob('contasuite-*')) - before).pop()
        shutil.copy2(root / 'private/service.json', backup / 'service-config.dpapi.json')
        hashes = {}
        for path in backup.rglob('*'):
            if not path.is_file() or path == backup / 'sha256.json':
                continue
            h = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            hashes[path.relative_to(backup).as_posix()] = h.hexdigest()
        (backup / 'sha256.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
        from restore_postgres import verify

        verify(backup)
        for key in ('CS_STORAGE_ALLOWED_ROOTS', 'CS_LOCAL_IMPORT_ROOTS'):
            roots = json.loads(config.get(key, '[]'))
            if not any(folder.is_relative_to(Path(p)) for p in roots):
                roots.append(str(folder))
            if len(roots) > 20:
                raise ValueError('Demasiadas rutas autorizadas.')
            config[key] = json.dumps(roots)
        write_secret(root / 'private/service.json', config)
        os.environ.update(config, PYTHON_DOTENV_DISABLED='1', DATA_DIR=str(root / 'data'), SEED_DEMO='false')
        # Explicit non-destructive storage upgrade, only after the verified backup.
        migration_env = os.environ.copy()
        result = subprocess.run(
            [
                str(root / 'runtime/python.exe'),
                '-B',
                str(root / 'app/scripts/schema_admin.py'),
                '--data-dir',
                str(root / 'data'),
                '--apply',
                '--backup',
                str(backup / 'database.dump'),
            ],
            env=migration_env,
            capture_output=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            timeout=180,
        )
        if result.returncode:
            raise RuntimeError('Falló la actualización explícita del esquema; no se encoló el origen.')
        from app.database import SessionLocal, engine, DATA

        if str(engine.url.database) != values['database']:
            raise RuntimeError('Conexión de catálogo incorrecta.')
        from app.schema_compatibility import assert_schema

        assert_schema(engine)
        from app.models import StorageSource, StorageIndexJob
        from app.storage.service import StorageService, StorageActor
        from app.storage.settings import StorageSettings
        from app.storage.connector import ConnectorService
        from app.storage.router import SourceConfiguration
        from app.storage.indexer import LocalIndexer
        from sqlalchemy import select

        actor = StorageActor('windows_operator:' + getpass.getuser(), admin=True)
        service = StorageService(SessionLocal, StorageSettings.from_environment(DATA))
        connector = ConnectorService(service)
        with SessionLocal() as db:
            source = db.scalar(
                select(StorageSource).where(
                    StorageSource.kind == 'local_folder', StorageSource.root_path == str(folder)
                )
            )
            ident = source.id if source else None
            if source:
                if db.scalar(
                    select(StorageIndexJob.id).where(
                        StorageIndexJob.source_id == ident, StorageIndexJob.status.in_(['queued', 'running'])
                    )
                ):
                    raise RuntimeError('Este origen ya tiene un trabajo activo; no se creó otro.')
                payload = SourceConfiguration(
                    label=source.label,
                    kind='local_folder',
                    root_path=str(folder),
                    enabled=True,
                    revision=source.revision,
                    interval_minutes=source.interval_minutes,
                    exclusions=list(dict.fromkeys(source.configuration.get('exclusions', []) + list(SECRET_PATTERNS))),
                )
            else:
                payload = SourceConfiguration(
                    label=folder.name + ' · prueba autorizada',
                    kind='local_folder',
                    root_path=str(folder),
                    enabled=True,
                    interval_minutes=0,
                    exclusions=list(SECRET_PATTERNS),
                )
        source = connector.save(actor, payload, ident)
        job = LocalIndexer(service).enqueue(actor, source['id'])
        report = {
            'source_id': source['id'],
            'job_id': job['id'],
            'root': str(folder),
            'backup': str(backup),
            'original_writes': False,
            'company_created_automatically': False,
        }
        (root / 'private/authorized-import.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        engine.dispose()
        return report
    finally:
        start(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--installation', type=Path, required=True)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--authorized', action='store_true')
    args = parser.parse_args()
    if not args.authorized:
        parser.error('Se requiere autorización explícita de la carpeta exacta.')
    print(json.dumps(prepare(args.installation.resolve(), args.folder)), flush=True)
