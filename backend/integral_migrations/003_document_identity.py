"""Add identity metadata only; legacy content is analyzed through authorized review, not migration."""
from app.document_identity import metadata
revision='integral_0003_document_identity'
down_revision='integral_0002'
def upgrade(connection):metadata.create_all(connection)
def downgrade(connection):raise RuntimeError('Identity decisions and review history must be preserved.')
