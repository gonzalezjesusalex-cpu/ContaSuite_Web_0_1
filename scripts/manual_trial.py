"""Manual test instance (INICIAR_PRUEBA_MANUAL.bat): synthetic data only, apart from every real instance.

Never reads the .env or data/ of this folder (they belong to the archived 8000 instance). Everything lives in
%LOCALAPPDATA%\\ContaSuite\\prueba-manual: a SQLite database declared as a test (CS_TEST_SQLITE=1), its files, the
installation key for the first administrator and an example company folder for the agent. Starts the API on
the first free port of 8090-8099 and the local agent in linked mode (with its notification-area icon), and opens the browser.
`--reset` keeps the previous trial renamed (never deleted) and starts a new one.
"""

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PORTS = range(8090, 8100)
AGENT_PORT = 47865


def free(port):
    with socket.socket() as s:
        return s.connect_ex(('127.0.0.1', port)) != 0


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=True)
    keys = folder / 'clave-instalacion.json'
    if not keys.is_file():
        keys.write_text(json.dumps({'app_token': secrets.token_urlsafe(24)}), encoding='utf-8')
    # Example company folder for «Analizar carpeta»: synthetic files only; the .key must never be listed.
    company = folder / 'empresas' / 'Empresa Demo'
    if not company.is_dir():
        company.mkdir(parents=True)
        (company / 'factura-demo.xml').write_text(
            '<?xml version="1.0" encoding="UTF-8"?><cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
            'Version="4.0" Total="1160.00"/>',
            encoding='utf-8',
        )
        (company / 'notas.txt').write_text('Archivo de ejemplo para la prueba manual.\n', encoding='utf-8')
        (company / 'llave-privada-demo.key').write_bytes(b'NO-DEBE-LISTARSE')
    return json.loads(keys.read_text(encoding='utf-8'))['app_token']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reset', action='store_true', help='Keep the previous trial renamed and start a new one')
    args = parser.parse_args()
    folder = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ContaSuite' / 'prueba-manual'
    if args.reset and folder.exists():
        kept = folder.with_name('prueba-manual-anterior-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
        folder.rename(kept)
        print('Prueba anterior conservada en ' + str(kept))
    if not (ROOT / 'frontend/dist/index.html').is_file():
        raise SystemExit('Falta frontend/dist. Ejecuta CONSTRUIR_FRONTEND.bat.')
    port = next((p for p in PORTS if free(p)), None)
    if port is None:
        raise SystemExit('Los puertos 8090-8099 están ocupados: cierra la otra prueba manual.')
    base = 'http://127.0.0.1:' + str(port)
    app_token = prepare(folder)
    env = {
        **os.environ,
        'PYTHON_DOTENV_DISABLED': '1',
        'CS_TEST_SQLITE': '1',
        'DATABASE_URL': 'sqlite:///' + (folder / 'prueba.db').as_posix(),
        'DATA_DIR': str(folder / 'data'),
        'APP_TOKEN': app_token,
        'SEED_DEMO': 'false',
        'CS_STORAGE_ALLOWED_ROOTS': '[]',
        'CS_STORAGE_SMB_ALLOWED_ROOTS': '[]',
        'PYTHONPATH': str(ROOT / 'backend'),
        'NO_PROXY': '127.0.0.1,localhost',
    }
    for key in ('AGENT_TOKEN', 'CS_ALLOW_SHARED_AGENT_TOKEN', 'CONTA_AGENT_TOKEN'):
        env.pop(key, None)
    if not (folder / 'prueba.db').is_file():
        print('Creando la base de prueba…')
        subprocess.run(
            [sys.executable, str(ROOT / 'scripts/schema_admin.py'), '--data-dir', env['DATA_DIR'], '--new', '--apply'],
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    else:
        # A trial created with an earlier version: update its schema, keeping a copy first (plan v1.1 adds cs_0018+).
        import shutil

        backup = folder / ('prueba-antes-de-actualizar-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.db')
        shutil.copy2(folder / 'prueba.db', backup)
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / 'scripts/schema_admin.py'),
                '--data-dir',
                env['DATA_DIR'],
                '--apply',
                '--backup',
                str(backup),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
        )
        if result.returncode:
            raise SystemExit('No se pudo actualizar la base de prueba; usa INICIAR_PRUEBA_MANUAL.bat --reset.')
    # Password manager (plan v1.1): a DPAPI keyring of this trial only, inside its own data folder.
    if os.name == 'nt' and not (Path(env['DATA_DIR']) / 'vault' / 'keyring.dpapi').is_file():
        subprocess.run(
            [sys.executable, str(ROOT / 'scripts/vault_keyring.py'), '--data-dir', env['DATA_DIR'], '--init'],
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    api = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
        cwd=ROOT / 'backend',
        env=env,
    )
    agent = None
    try:
        for _ in range(120):
            try:
                with urlopen(base + '/api/health', timeout=1):
                    break
            except OSError:
                if api.poll() is not None:
                    raise SystemExit('El servidor de prueba no inició; revisa los mensajes de arriba.') from None
                time.sleep(0.5)
        if free(AGENT_PORT):
            config = folder / 'agente.json'
            config.write_text(
                json.dumps(
                    {
                        'api_url': base,
                        'local_port': AGENT_PORT,
                        'app_origins': [base, 'http://localhost:' + str(port)],
                        'log_file': str(folder / 'agente.log'),
                    }
                ),
                encoding='utf-8',
            )
            agent = subprocess.Popen([sys.executable, str(ROOT / 'agent/agent.py'), '--config', str(config)], env=env)
            agent_note = 'Agente local iniciado (icono junto al reloj); se vincula al iniciar sesión.'
        else:
            agent_note = f'El puerto {AGENT_PORT} ya está en uso (otro agente): no se inició el agente de prueba.'
        webbrowser.open(base)
        print(
            '\n'
            + '=' * 72
            + f'\nContaSuite · prueba manual en {base}  (datos sintéticos, aparte de toda instancia real)\n'
            + f'Clave para crear el primer administrador: {app_token}\n'
            + f'{agent_note}\n'
            + f'Carpeta de ejemplo para autorizar en Configuración › Agentes locales:\n  {folder / "empresas"}\n'
            + f'Ruta de la empresa de ejemplo (Editar › Expediente digital):\n  {folder / "empresas" / "Empresa Demo"}\n'
            + f'Datos de esta prueba: {folder}\n'
            + 'Ctrl+C para detener. Para empezar de cero: INICIAR_PRUEBA_MANUAL.bat --reset\n'
            + '=' * 72
            + '\n'
        )
        api.wait()
    except KeyboardInterrupt:
        print('\nDeteniendo la prueba…')
    finally:
        for process in (agent, api):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == '__main__':
    main()
