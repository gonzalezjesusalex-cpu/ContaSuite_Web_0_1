"""Additive, explicit only. Never include in startup. Requires existing companies."""
from app.company_lifecycle import metadata
revision = 'company_archive_0001'

def upgrade(connection):
    metadata.create_all(connection)

def downgrade(connection):
    raise RuntimeError('Reversión destructiva deshabilitada: conservar identidad e historial.')
