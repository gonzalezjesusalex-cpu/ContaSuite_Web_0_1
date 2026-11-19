"""Prepared additive migration: five obligations of the Excel «Control de obligaciones» (cambio 3A.5).

Not part of the automatic chain and never imported by startup. An operator applies it explicitly, with a backup,
after 001. Idempotent: an obligation that already exists (same name, case-insensitive) is left untouched.
"""
from sqlalchemy import func, select
from app.fiscal_control import catalog, EXTRA, INITIAL

revision = 'fiscal_0002'
down_revision = 'fiscal_0001'


def upgrade(connection):
    existing = {label.casefold() for (label,) in connection.execute(select(catalog.c.label))}
    for i, (label, periodicity) in enumerate(EXTRA):
        if label.casefold() in existing:
            continue
        ident = 'fiscal-' + str(len(INITIAL) + i + 1).zfill(2)
        if connection.execute(select(func.count()).select_from(catalog).where(catalog.c.id == ident)).scalar():
            continue
        connection.execute(catalog.insert().values(id=ident, label=label, periodicity=periodicity))


def downgrade(connection):
    raise RuntimeError('Reversión destructiva deshabilitada: conservar registros e historial.')
