"""Persistent virtual index of each company's folder: virtual_scans and virtual_files.

Additive and idempotent: two new, empty tables. Nothing is read from or written to any document folder by this
revision; the rows appear only when a user analyzes a folder with the local agent. No existing table changes.
Apply only through scripts/schema_admin.py with a backup (a database without these tables is reported as
incompatible at startup, on purpose).
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0014_virtual_index'
down_revision = 'cs_0013_agent_links'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('virtual_scans'):
        op.create_table(
            'virtual_scans',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('job_id', sa.String(36), nullable=True, index=True),
            sa.Column('requested_by', sa.String(36), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('complete', sa.Boolean(), nullable=False),
            sa.Column('total', sa.Integer(), nullable=False),
            sa.Column('added', sa.Integer(), nullable=False),
            sa.Column('changed', sa.Integer(), nullable=False),
            sa.Column('moved', sa.Integer(), nullable=False),
            sa.Column('restored', sa.Integer(), nullable=False),
            sa.Column('missing', sa.Integer(), nullable=False),
        )
    if not inspector.has_table('virtual_files'):
        op.create_table(
            'virtual_files',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('path', sa.String(1000), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('size', sa.BigInteger(), nullable=False),
            sa.Column('mtime_ns', sa.BigInteger(), nullable=True),
            sa.Column('sha256', sa.String(64), nullable=True, index=True),
            sa.Column('group_key', sa.String(30), nullable=False),
            sa.Column('section', sa.String(30), nullable=False, index=True),
            sa.Column('virtual_path', sa.String(1200), nullable=False),
            sa.Column('state', sa.String(12), nullable=False),
            sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
            sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
            sa.Column('scan_id', sa.String(36), nullable=False, index=True),
            sa.Column('missing_since', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_change', sa.String(10), nullable=False),
            sa.Column('last_change_scan', sa.String(36), nullable=True, index=True),
            sa.Column('moved_from', sa.String(1000), nullable=True),
            sa.UniqueConstraint('company_id', 'path', name='uq_virtual_files_company_path'),
        )


def downgrade():
    raise RuntimeError('Retirar el índice virtual perdería el historial de cambios de las carpetas; sin reversión.')
