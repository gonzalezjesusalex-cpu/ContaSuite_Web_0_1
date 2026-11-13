"""Offline isolated local installation. Never attaches to an existing cluster/database."""

import base64, json, os, re, secrets, shutil, socket, subprocess, sys, time
from pathlib import Path
from uuid import uuid4
from secure_config import crypt, load

FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def run(args, env=None, timeout=180):
    background = Path(args[0]).name.lower() == 'pg_ctl.exe' and 'start' in args
    result = subprocess.run(
        [str(v) for v in args],
        env=env,
        stdout=subprocess.DEVNULL if background else subprocess.PIPE,
        stderr=subprocess.DEVNULL if background else subprocess.PIPE,
        timeout=timeout,
        creationflags=FLAGS,
    )
    if result.returncode:
        raise RuntimeError(
            'Falló ' + Path(args[0]).name + '. Consulta el registro de instalación; no se muestran secretos.'
        )
    return result


def free_port(port=0):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', port))
        return sock.getsockname()[1]


def write_secret(path, values):
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.pending')
    try:
        temporary.write_text(
            json.dumps(
                {
                    'format': 'contasuite-dpapi-machine-v1',
                    'protected': base64.b64encode(crypt(json.dumps(values).encode())).decode('ascii'),
                }
            ),
            encoding='utf-8',
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_roots(values, forbidden=()):
    if len(values) > 20:
        raise ValueError('Autoriza como máximo 20 carpetas; selecciona sólo las necesarias para cada análisis.')
    roots = [Path(v) for v in values]
    if any(not p.is_absolute() or str(p).startswith(('\\\\', '//')) for p in roots):
        raise ValueError('Usa carpetas locales absolutas; SMB se configura por separado.')
    if os.name == 'nt':
        import ctypes

        if any(ctypes.windll.kernel32.GetDriveTypeW(str(p.anchor)) != 3 for p in roots):
            raise ValueError('Usa un disco local fijo; las unidades de red se configuran mediante SMB.')
    for i, a in enumerate(roots):
        for b in roots[i + 1 :]:
            if a.is_relative_to(b) or b.is_relative_to(a):
                raise ValueError('Las carpetas no pueden repetirse ni estar dentro de otra autorizada.')
        if any(a.resolve().is_relative_to(p.resolve()) or p.resolve().is_relative_to(a.resolve()) for p in forbidden):
            raise ValueError('No autorices carpetas que contengan la instalación ni el instalador.')
    return [str(p) for p in roots]


def validate(source, destination, username, password, port, roots):
    if not destination.is_absolute() or destination.exists():
        raise ValueError('Elige una carpeta nueva de instalación.')
    if str(destination).startswith(('\\\\', '//')):
        raise ValueError('La instalación debe estar en un disco local.')
    if destination.resolve().is_relative_to(source.resolve()) or source.resolve().is_relative_to(destination.resolve()):
        raise ValueError('La instalación debe quedar fuera de la carpeta del instalador.')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}', username):
        raise ValueError('Usuario: 3 a 64 letras, números, guion o punto.')
    if not 12 <= len(password) <= 128:
        raise ValueError('La contraseña debe tener entre 12 y 128 caracteres.')
    if port in (8000, 8062) or not 1024 <= port <= 65535:
        raise ValueError('Usa otro puerto, por ejemplo 8072; 8000 y 8062 se conservan para instalaciones anteriores.')
    roots = validate_roots(roots, forbidden=(destination, source))
    free_port(port)
    return roots


def marker(root):
    values = json.loads((root / 'LOCAL_INSTALLATION.json').read_text(encoding='utf-8'))
    if (
        values.get('format') != 'contasuite-isolated-local-v1'
        or values.get('root') != str(root.resolve())
        or not re.fullmatch(r'contasuite_local_[a-f0-9]{12}', values.get('database', ''))
    ):
        raise ValueError('No es una instalación local verificable.')
    return values


def stop_postgres(root):
    marker(root)
    run([root / 'postgresql/bin/pg_ctl.exe', '-D', root / 'database', '-m', 'fast', '-w', 'stop'], timeout=60)


def start_postgres(root):
    values = marker(root)
    status = subprocess.run(
        [str(root / 'postgresql/bin/pg_ctl.exe'), '-D', str(root / 'database'), 'status'],
        capture_output=True,
        creationflags=FLAGS,
    )
    if status.returncode:
        free_port(values['pg_port'])
        run(
            [
                root / 'postgresql/bin/pg_ctl.exe',
                '-D',
                root / 'database',
                '-l',
                root / 'logs/postgres.log',
                '-w',
                'start',
            ],
            timeout=60,
        )
    # Prove the server on that port is our cluster, before any app/database operation.
    import psycopg

    config = load(root / 'private/database-admin.json')
    with psycopg.connect(
        host='127.0.0.1',
        port=values['pg_port'],
        user='cs_bootstrap',
        password=config['password'],
        dbname='postgres',
        connect_timeout=5,
    ) as db:
        if Path(db.execute('SHOW data_directory').fetchone()[0]).resolve() != (root / 'database').resolve():
            raise RuntimeError('El puerto no pertenece a esta instalación.')


def install(source, destination, username, password, port, roots, progress=lambda value: None):
    roots = validate(source, destination, username, password, port, roots)
    from install_release import verify

    progress('Verificando el paquete…')
    verify(source)
    progress('Copiando aplicación, Python y PostgreSQL privados…')
    shutil.copytree(source, destination)
    root = destination.resolve()
    for directory in ('private', 'data', 'logs'):
        (root / directory).mkdir(exist_ok=False)
    # Per-user ACL, inherited by all new credentials/database files.
    import getpass

    run(['icacls.exe', root, '/inheritance:r', '/grant:r', getpass.getuser() + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'])
    database = 'contasuite_local_' + uuid4().hex[:12]
    pg_port = free_port()
    values = {
        'format': 'contasuite-isolated-local-v1',
        'root': str(root),
        'database': database,
        'pg_port': pg_port,
        'api_port': port,
        'username': username.lower(),
    }
    (root / 'LOCAL_INSTALLATION.json').write_text(json.dumps(values, indent=2), encoding='utf-8')
    admin_password = secrets.token_urlsafe(36)
    app_password = secrets.token_urlsafe(36)
    write_secret(root / 'private/database-admin.json', {'password': admin_password})
    password_file = root / 'private/init-password.tmp'
    progress('Creando un clúster PostgreSQL nuevo y aislado…')
    password_file.write_text(admin_password, encoding='utf-8')
    try:
        run(
            [
                root / 'postgresql/bin/initdb.exe',
                '-D',
                root / 'database',
                '-U',
                'cs_bootstrap',
                '--pwfile=' + str(password_file),
                '--auth=scram-sha-256',
                '--encoding=UTF8',
                '--locale=C',
            ],
            timeout=120,
        )
    finally:
        password_file.unlink(missing_ok=True)
    with (root / 'database/postgresql.conf').open('a', encoding='utf-8') as stream:
        stream.write(
            f"\nlisten_addresses='127.0.0.1'\nport={pg_port}\nlog_statement='none'\nlog_min_error_statement='panic'\n"
        )
    started = False
    try:
        start_postgres(root)
        started = True
        import psycopg
        from psycopg import sql

        with psycopg.connect(
            host='127.0.0.1',
            port=pg_port,
            user='cs_bootstrap',
            password=admin_password,
            dbname='postgres',
            autocommit=True,
        ) as db:
            db.execute(
                sql.SQL('CREATE ROLE cs_app LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE').format(
                    sql.Literal(app_password)
                )
            )
            db.execute(sql.SQL('CREATE DATABASE {} OWNER cs_app').format(sql.Identifier(database)))
        from sqlalchemy.engine import URL

        config = {
            'DATABASE_URL': URL.create(
                'postgresql+psycopg',
                username='cs_app',
                password=app_password,
                host='127.0.0.1',
                port=pg_port,
                database=database,
            ).render_as_string(hide_password=False),
            'APP_TOKEN': secrets.token_urlsafe(48),
            'AGENT_TOKEN': secrets.token_urlsafe(48),
            'CS_ALLOWED_HOSTS': '["127.0.0.1","localhost"]',
            'CS_STORAGE_ALLOWED_ROOTS': json.dumps(roots),
            'CS_STORAGE_SMB_ALLOWED_ROOTS': '[]',
            'CS_LOCAL_IMPORT_ENABLED': '1',
            'CS_LOCAL_IMPORT_DATABASE': database,
            'CS_LOCAL_IMPORT_ROOTS': json.dumps(roots),
        }
        write_secret(root / 'private/service.json', config)
        env = os.environ.copy()
        env.update(config, PYTHON_DOTENV_DISABLED='1', DATA_DIR=str(root / 'data'), SEED_DEMO='false')
        progress('Aplicando esquema sólo en la base nueva…')
        run(
            [
                root / 'runtime/python.exe',
                '-B',
                root / 'app/scripts/schema_admin.py',
                '--data-dir',
                root / 'data',
                '--apply',
                '--new',
            ],
            env,
        )
        progress('Creando tu cuenta administradora…')
        # Stdin contains a synthetic/entered password; never in arguments or a file.
        code = "import sys,json,os; from fastapi.testclient import TestClient; from app.main import app; v=json.load(sys.stdin); client=TestClient(app,base_url='http://127.0.0.1'); client.__enter__(); response=client.post('/api/auth/bootstrap',headers={'Authorization':'Bearer '+os.environ['APP_TOKEN']},json=v); assert response.status_code==201; client.__exit__(None,None,None)"
        response = subprocess.run(
            [str(root / 'runtime/python.exe'), '-B', '-c', code],
            input=json.dumps({'username': username.lower(), 'display_name': username, 'password': password}),
            env=env,
            text=True,
            capture_output=True,
            creationflags=FLAGS,
            timeout=90,
        )
        if response.returncode:
            raise RuntimeError('No se pudo crear la cuenta inicial; instalación conservada para diagnóstico.')
        (root / 'INSTALACION_COMPLETA.txt').write_text(
            'Instalación local independiente. Usuario: '
            + username.lower()
            + '\nURL: http://localhost:'
            + str(port)
            + '\nSin carpetas importadas.\n',
            encoding='utf-8',
        )
        progress('Instalación preparada. No se ha leído ni importado ninguna carpeta.')
        return values
    finally:
        if started or (root / 'database/postmaster.pid').is_file():
            stop_postgres(root)
