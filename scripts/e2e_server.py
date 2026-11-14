"""Synthetic ContaSuite server for the Playwright E2E smoke test.

Creates a throwaway SQLite database and data folder in the system temp directory, applies the schema
explicitly and serves the built frontend. It never reads .env and refuses any real database settings:
everything it needs comes from the E2E_* variables set by frontend/playwright.config.ts.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    port = int(os.environ.get('E2E_PORT', '8097'))
    if port in {8000, 8062, 8072}:
        raise SystemExit('E2E_PORT no puede usar los puertos de instancias reales (8000, 8062, 8072).')
    app_token = os.environ.get('E2E_APP_TOKEN', '')
    if len(app_token) < 24:
        raise SystemExit('E2E_APP_TOKEN debe tener al menos 24 caracteres (lo genera playwright.config.ts).')
    if not (ROOT / 'frontend' / 'dist' / 'index.html').is_file():
        raise SystemExit('Falta frontend/dist: ejecuta antes npm --prefix frontend run build.')
    # Playwright stops this process abruptly, so cleanup on exit is not guaranteed: reuse one folder per
    # port and empty it at start, which leaves at most one synthetic folder behind.
    work = Path(tempfile.gettempdir()) / ('contasuite-e2e-' + str(port))
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    data = work / 'data'
    os.environ.update(
        {
            'PYTHON_DOTENV_DISABLED': '1',
            'DATABASE_URL': 'sqlite:///' + (work / 'e2e.db').as_posix(),
            'DATA_DIR': str(data),
            'APP_TOKEN': app_token,
            'AGENT_TOKEN': os.environ.get('E2E_AGENT_TOKEN', app_token + '-agent'),
            'SEED_DEMO': 'false',
            'CS_PORT': str(port),
            'CS_STORAGE_ALLOWED_ROOTS': '[]',
            'CS_STORAGE_SMB_ALLOWED_ROOTS': '[]',
        }
    )
    try:
        subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'schema_admin.py'), '--data-dir', str(data), '--new', '--apply'],
            check=True,
            env=os.environ,
        )
        sys.path.insert(0, str(ROOT / 'backend'))
        import uvicorn

        from app.main import app

        uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
