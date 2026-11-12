"""Prepared additive migration. Not part of the automatic CS-Storage chain.

An operator must explicitly supply a connection after approving a backup/rehearsal.
Never imported by application startup. No legacy records are converted implicitly.
"""
from sqlalchemy import select
from app.fiscal_control import metadata,catalog,INITIAL

revision='fiscal_0001'
down_revision=None

def upgrade(connection):
    metadata.create_all(connection)
    for i,label in enumerate(INITIAL):
        ident='fiscal-'+str(i+1).zfill(2)
        if not connection.execute(select(catalog.c.id).where(catalog.c.id==ident)).first():
            connection.execute(catalog.insert().values(id=ident,label=label,periodicity='monthly'))

def downgrade(connection):
    raise RuntimeError('Reversión destructiva deshabilitada: conservar registros e historial.')
