"""First-run configuration. Standard-library only; no secrets in the distributed ZIP."""

import argparse
import json
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]


def launcher_port():
    """INICIAR_* launchers serve the old instance kept in this folder: 8000 unless CS_PORT says otherwise."""
    scripts = str(Path(__file__).resolve().parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from service_runtime import LEGACY_PORT, default_port

    try:
        return default_port(LEGACY_PORT)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None


def configure(portable=False):
    port = launcher_port()
    env_path = root / '.env'
    if not env_path.exists():
        app = secrets.token_urlsafe(32)
        agent = secrets.token_urlsafe(32)
        db_password = secrets.token_hex(18)
        database = (
            'sqlite:///./data/contasuite.db'
            if portable
            else f'postgresql+psycopg://contasuite:{db_password}@127.0.0.1:5432/contasuite'
        )
        # Portable trials use SQLite, which the application only accepts when declared as a test.
        test_flag = 'CS_TEST_SQLITE=1\n' if portable else ''
        env_path.write_text(
            f'DATABASE_URL={database}\nPOSTGRES_PASSWORD={db_password}\nAPP_TOKEN={app}\nAGENT_TOKEN={agent}\nSEED_DEMO=false\n{test_flag}CS_STORAGE_ALLOWED_ROOTS=[]\nCS_STORAGE_MAX_FILE_MB=25\n',
            encoding='utf-8',
        )
    values = dict(
        line.split('=', 1)
        for line in env_path.read_text(encoding='utf-8').splitlines()
        if '=' in line and not line.startswith('#')
    )
    (root / 'data').mkdir(exist_ok=True)
    example = root / 'agent' / 'config.json'
    if not example.exists():
        example.write_text(
            json.dumps(
                {
                    'api_url': f'http://127.0.0.1:{port}',
                    'agent_id': 'oficina-windows',
                    'allowed_roots': [str(root / 'data' / 'empresas')],
                    'token': values['AGENT_TOKEN'],
                },
                indent=2,
            ),
            encoding='utf-8',
        )
    (root / 'data' / 'empresas').mkdir(exist_ok=True)
    if not (root / 'frontend' / 'dist' / 'index.html').is_file():
        raise SystemExit('Falta frontend/dist. Ejecuta CONSTRUIR_FRONTEND.bat.')
    if not values['DATABASE_URL'].startswith('sqlite'):
        if not shutil.which('docker'):
            raise SystemExit(
                'Esta instalación usa PostgreSQL. Inicia Docker Desktop o configura DATABASE_URL en .env. Para una instalación nueva de prueba usa INICIAR_PRUEBA.bat.'
            )
        try:
            subprocess.run(['docker', 'compose', 'up', '-d', '--wait', 'db'], cwd=root, check=True)
        except subprocess.CalledProcessError:
            raise SystemExit('No se pudo iniciar PostgreSQL. Comprueba Docker Desktop y el puerto 5432.')
    print(f'\nContaSuite Web 0.1 - http://127.0.0.1:{port}')
    print('Clave para crear el primer administrador: ' + values['APP_TOKEN'])
    print('Si ya existen cuentas, ingresa con usuario y contraseña; esta clave no restablece el acceso.')
    print('Conserva esta ventana abierta. Ctrl+C para detener.\n')
    return values


if __name__ == '__main__':
    if sys.version_info < (3, 11):
        raise SystemExit('Se necesita Python 3.11 o posterior (recomendado: 3.12).')
    parser = argparse.ArgumentParser()
    parser.add_argument('--portable', action='store_true')
    args = parser.parse_args()
    configure(args.portable)
