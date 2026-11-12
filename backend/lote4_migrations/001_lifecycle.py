"""Explicit additive extension; never import from startup. No historical conversion."""
from app.lote4_lifecycle import metadata
revision='lote4_lifecycle_0001'
def upgrade(connection):metadata.create_all(connection)
def downgrade(connection):raise RuntimeError('Conservar historial; reversión destructiva deshabilitada.')
