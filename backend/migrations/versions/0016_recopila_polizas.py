"""Recopila: persistencia de polizas, relacion poliza-CFDI con su origen y ajustes manuales.

Additive and idempotent: three new, empty tables. Nothing is read from or written to any document folder by this
revision and no existing table changes. Apply only through scripts/schema_admin.py with a backup (a database without
these tables is reported as incompatible at startup, on purpose).
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0016_recopila_policies'
down_revision = 'cs_0015_virtual_copy'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('recopila_policies'):
        op.create_table(
            'recopila_policies',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('run_id', sa.String(36), sa.ForeignKey('recopila_runs.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('idx', sa.Integer(), nullable=False),
            sa.Column('policy_type', sa.String(40), nullable=False),
            sa.Column('policy_date', sa.String(10), nullable=False),
            sa.Column('period', sa.String(7), nullable=False, index=True),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('uuids', sa.JSON(), nullable=False),
            sa.UniqueConstraint('run_id', 'idx', name='uq_recopila_policies_run_idx'),
        )
    if not inspector.has_table('recopila_policy_cfdis'):
        op.create_table(
            'recopila_policy_cfdis',
            sa.Column('policy_id', sa.String(36), sa.ForeignKey('recopila_policies.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('cfdi_uuid', sa.String(36), primary_key=True),
            sa.Column('origin', sa.String(10), nullable=False),
            sa.Column('state', sa.String(10), nullable=False),
            sa.Column('decided_by', sa.String(100), nullable=True),
            sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        )
    if not inspector.has_table('recopila_adjustments'):
        op.create_table(
            'recopila_adjustments',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('run_id', sa.String(36), sa.ForeignKey('recopila_runs.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('policy_idx', sa.Integer(), nullable=False),
            sa.Column('action', sa.String(10), nullable=False),
            sa.Column('target', sa.String(1000), nullable=False),
            sa.Column('cfdi_uuid', sa.String(36), nullable=True),
            sa.Column('actor_id', sa.String(100), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    raise RuntimeError('Retirar estas tablas perdería los ajustes manuales y su autoría; sin reversión.')
