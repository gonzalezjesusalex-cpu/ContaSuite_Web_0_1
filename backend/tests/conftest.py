"""Suite-wide test environment, loaded by pytest before any test module imports the application."""

import os

# The suite runs on synthetic SQLite databases: declare it explicitly (app.database refuses SQLite
# otherwise, plan point 19). Subprocesses started by the tests inherit it.
os.environ['CS_TEST_SQLITE'] = '1'


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _locked_vaults():
    """Unlocked vaults live in process memory (app/vault_session.py): every test starts and ends locked."""
    yield
    from app import vault_session

    vault_session.lock_all()
