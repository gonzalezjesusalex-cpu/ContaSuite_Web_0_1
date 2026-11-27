"""Renovación del gestor de contraseñas, fase 4: import templates.

Additive and idempotent: one table, `vault_import_templates`, that remembers how each column of an Excel format was
assigned (header signature → mapping), so the same format is recognized the next time. It never stores a value of a
cell, only header texts and destinations. Apply only through scripts/schema_admin.py with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0025_vault_import_templates'
down_revision = 'cs_0024_vault_types_classes'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('vault_credentials') or inspector.has_table('vault_import_templates'):
        return
    op.create_table(
        'vault_import_templates',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('header_signature', sa.String(64), nullable=False, unique=True),
        sa.Column('mapping', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.String(100), nullable=False),
    )


def downgrade():
    raise RuntimeError('Las plantillas de importación sólo guardan encabezados; sin reversión automática.')
