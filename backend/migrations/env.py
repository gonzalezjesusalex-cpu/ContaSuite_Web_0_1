from alembic import context
from app.database import engine

config = context.config


def run(connection):
    context.configure(connection=connection, render_as_batch=connection.dialect.name == 'sqlite')
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError('CS-Storage requires an online connection to validate the existing schema; use a disposable local database for testing.')
elif config.attributes.get('connection') is not None:
    run(config.attributes['connection'])
else:
    with engine.begin() as connection:
        run(connection)
