"""DATABASE_URL must be configured explicitly; there are no built-in or example credentials."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def import_database(tmp_path, url):
    """Import app.database in a fresh process (no .env, no inherited DATABASE_URL)."""
    env = {k: v for k, v in os.environ.items() if k not in {'DATABASE_URL', 'APP_TOKEN', 'AGENT_TOKEN'}}
    env.update(PYTHON_DOTENV_DISABLED='1', DATA_DIR=str(tmp_path / 'data'), PYTHONIOENCODING='utf-8')
    if url is not None:
        env['DATABASE_URL'] = url
    return subprocess.run(
        [sys.executable, '-B', '-c', 'import app.database; print("ok")'],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        encoding='utf-8',
        timeout=60,
    )


def test_missing_database_url_stops_with_clear_message(tmp_path):
    result = import_database(tmp_path, None)
    assert result.returncode != 0
    assert 'DATABASE_URL no está configurada' in result.stderr


@pytest.mark.parametrize(
    'url',
    [
        'postgresql+psycopg://contasuite:contasuite@127.0.0.1:5432/contasuite',
        'postgresql+psycopg://contasuite:CAMBIAR@127.0.0.1:5432/contasuite',
    ],
)
def test_example_credentials_are_rejected(tmp_path, url):
    result = import_database(tmp_path, url)
    assert result.returncode != 0
    assert 'credenciales de ejemplo' in result.stderr
    assert 'contasuite:contasuite' not in result.stderr and 'CAMBIAR@' not in result.stderr


def test_explicit_database_url_is_accepted(tmp_path):
    result = import_database(tmp_path, 'sqlite:///' + str(tmp_path / 'explicit.db'))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'ok'
