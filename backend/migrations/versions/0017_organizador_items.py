"""CFDI (Organizador): archivos revisados contra el expediente y su estado de guardado.

Additive and idempotent: one new, empty table. Nothing is read from or written to any document folder by this
revision and no existing table changes. Apply only through scripts/schema_admin.py with a backup (a database without
this table is reported as incompatible at startup, on purpose).
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0017_organizador_items'
down_revision = 'cs_0016_recopila_policies'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table('organizador_items'):
        return
    op.create_table(
        'organizador_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('run_id', sa.String(36), sa.ForeignKey('organizador_runs.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id'), nullable=True, index=True),
        sa.Column('rel_path', sa.String(700), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('ext', sa.String(8), nullable=False),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('uuid', sa.String(36), nullable=True, index=True),
        sa.Column('folder_period', sa.String(7), nullable=False),
        sa.Column('xml_period', sa.String(7), nullable=True),
        sa.Column('state', sa.String(14), nullable=False),
        sa.Column('reasons', sa.JSON(), nullable=False),
        sa.Column('document_id', sa.String(36), nullable=True),
        sa.Column('decided_by', sa.String(100), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decided_period', sa.String(7), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('run_id', 'rel_path', name='uq_organizador_items_run_path'),
    )


def downgrade():
    raise RuntimeError('Retirar esta tabla perdería las decisiones de revisión y su autoría; sin reversión.')
