"""DATABASE_URL must be configured explicitly; there are no built-in or example credentials."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def import_database(tmp_path, url, test_sqlite=None):
    """Import app.database in a fresh process (no .env, no inherited DATABASE_URL or SQLite test flag)."""
    env = {
        k: v for k, v in os.environ.items() if k not in {'DATABASE_URL', 'APP_TOKEN', 'AGENT_TOKEN', 'CS_TEST_SQLITE'}
    }
    env.update(PYTHON_DOTENV_DISABLED='1', DATA_DIR=str(tmp_path / 'data'), PYTHONIOENCODING='utf-8')
    if url is not None:
        env['DATABASE_URL'] = url
    if test_sqlite is not None:
        env['CS_TEST_SQLITE'] = test_sqlite
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
    result = import_database(tmp_path, 'sqlite:///' + str(tmp_path / 'explicit.db'), test_sqlite='1')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'ok'


@pytest.mark.parametrize('flag', [None, '', '0', 'true', 'yes'])
@pytest.mark.parametrize('database', ['file', ':memory:'])
def test_sqlite_requires_explicit_test_declaration(tmp_path, flag, database):
    # Plan point 19: advisory locks do nothing on SQLite, so production must use PostgreSQL.
    url = 'sqlite:///' + (str(tmp_path / 'trial.db') if database == 'file' else ':memory:')
    result = import_database(tmp_path, url, test_sqlite=flag)
    assert result.returncode != 0
    assert 'SQLite sólo se admite en pruebas' in result.stderr
    assert 'CS_TEST_SQLITE=1' in result.stderr
    assert not (tmp_path / 'trial.db').exists()


def test_postgresql_needs_no_test_declaration(tmp_path):
    # The engine is created lazily: importing must not require a reachable server.
    result = import_database(tmp_path, 'postgresql+psycopg://contasuite_app:synthetic-only@127.0.0.1:5432/contasuite')
    assert result.returncode == 0, result.stderr
