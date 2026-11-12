"""Run explicit, versioned upgrades against the configured database (or a supplied test engine)."""
from pathlib import Path
from alembic import command
from alembic.config import Config


def upgrade_storage(engine):
    backend = Path(__file__).resolve().parents[2]
    configuration = Config(str(backend / 'alembic.ini'))
    configuration.set_main_option('script_location', str(backend / 'migrations'))
    with engine.begin() as connection:
        # SQLite DDL must be inside an actual transaction, not only SQLAlchemy's logical one.
        if connection.dialect.name == 'sqlite':
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        configuration.attributes['connection'] = connection
        command.upgrade(configuration, 'head')


if __name__ == '__main__':
    from ..database import engine
    upgrade_storage(engine)
    print('CS-Storage schema upgraded. No source documents were opened or modified.')
