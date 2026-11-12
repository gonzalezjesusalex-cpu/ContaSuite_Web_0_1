"""Explicit additive migration. Preserves surviving legacy current decisions."""
from app.evidence_history import metadata,capture_legacy
revision='integral_0002'
down_revision='integral_0001'
def upgrade(connection):
    metadata.create_all(connection)
    capture_legacy(connection)
def downgrade(connection):raise RuntimeError('Never delete verification history.')
