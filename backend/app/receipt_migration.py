"""Actualiza Recibos sin cambiar los PDF ni los folios emitidos."""
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable
from .models import Receipt


def migrate_receipts(engine):
    inspector=inspect(engine)
    if not inspector.has_table('receipts'):return
    columns={c['name']:c for c in inspector.get_columns('receipts')}
    if 'client_id' in columns and 'concept' in columns and columns['company_id']['nullable']:return
    with engine.begin() as connection:
        if engine.dialect.name=='sqlite':
            connection.execute(text('BEGIN IMMEDIATE'))
            # No incoming FK references this table. Copy records in one transaction.
            ddl=str(CreateTable(Receipt.__table__).compile(engine)).replace('CREATE TABLE receipts (','CREATE TABLE receipts_updated (',1)
            connection.execute(text(ddl))
            common=', '.join('"'+c.name+'"' for c in Receipt.__table__.columns if c.name in columns)
            connection.execute(text(f'INSERT INTO receipts_updated ({common}) SELECT {common} FROM receipts'))
            connection.execute(text('DROP TABLE receipts'))
            connection.execute(text('ALTER TABLE receipts_updated RENAME TO receipts'))
            for index in Receipt.__table__.indexes:index.create(connection)
        else:
            connection.execute(text('ALTER TABLE receipts ALTER COLUMN company_id DROP NOT NULL'))
            if 'client_id' not in columns:connection.execute(text('ALTER TABLE receipts ADD COLUMN client_id VARCHAR(36)'))
            if 'concept' not in columns:connection.execute(text("ALTER TABLE receipts ADD COLUMN concept VARCHAR(1000) NOT NULL DEFAULT ''"))
            connection.execute(text('CREATE INDEX IF NOT EXISTS ix_receipts_client_id ON receipts (client_id)'))
