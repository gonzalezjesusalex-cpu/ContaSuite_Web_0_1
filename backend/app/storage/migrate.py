"""Run explicit, versioned upgrades against the configured database (or a supplied test engine)."""
from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

STORAGE_HEAD = 'cs_storage_0005'


def _configuration():
    backend = Path(__file__).resolve().parents[2]
    configuration = Config(str(backend / 'alembic.ini'))
    configuration.set_main_option('script_location', str(backend / 'migrations'))
    return configuration


def _upgrade(engine, target):
    configuration = _configuration()
    with engine.begin() as connection:
        # SQLite DDL must be inside an actual transaction, not only SQLAlchemy's logical one.
        if connection.dialect.name == 'sqlite':
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        configuration.attributes['connection'] = connection
        command.upgrade(configuration, target)


def upgrade_storage(engine):
    """CS-Storage revisions only (0001-0005), as before the unified baseline."""
    _upgrade(engine, STORAGE_HEAD)


def upgrade_schema(engine):
    """Whole application schema: the single Alembic chain up to head."""
    _upgrade(engine, 'head')


def schema_revision(engine):
    """Read-only: (current revision or None, head revision)."""
    head = ScriptDirectory.from_config(_configuration()).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    return current, head


if __name__ == '__main__':
    from ..database import engine
    upgrade_storage(engine)
    print('CS-Storage schema upgraded. No source documents were opened or modified.')
