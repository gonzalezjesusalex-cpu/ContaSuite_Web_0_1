"""Prepared additive migration: confirmed Excel-name -> company equivalences with history (cambio 3A.4).

Not part of the automatic chain and never imported by startup. An operator applies it explicitly, with a backup,
after 001. Creates two new tables only; no existing row is read or changed.
"""
from app.fiscal_equivalence import metadata

revision = 'fiscal_0003'
down_revision = 'fiscal_0002'


def upgrade(connection):
    metadata.create_all(connection)


def downgrade(connection):
    raise RuntimeError('Reversión destructiva deshabilitada: conservar equivalencias e historial.')
