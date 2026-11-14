"""Suite-wide test environment, loaded by pytest before any test module imports the application."""

import os

# The suite runs on synthetic SQLite databases: declare it explicitly (app.database refuses SQLite
# otherwise, plan point 19). Subprocesses started by the tests inherit it.
os.environ['CS_TEST_SQLITE'] = '1'
