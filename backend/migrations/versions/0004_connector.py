"""Connector configuration and independent scheduler health; additive, frozen migration."""
from alembic import op
import sqlalchemy as sa

revision = 'cs_storage_0004'
down_revision = 'cs_storage_0003'
branch_labels = None
depends_on = None


def upgrade():
    for column in [sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
                   sa.Column('interval_minutes', sa.Integer(), nullable=False, server_default='0'),
                   sa.Column('next_scan_at', sa.DateTime(timezone=True)),
                   sa.Column('checked_at', sa.DateTime(timezone=True)),
                   sa.Column('check_state', sa.String(30), nullable=False, server_default='unchecked'),
                   sa.Column('check_code', sa.String(40))]:
        op.add_column('storage_sources', column)
    op.create_table('storage_worker_state', sa.Column('id', sa.String(20), primary_key=True),
                    sa.Column('owner', sa.String(100), nullable=False),
                    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    raise RuntimeError('Forward-only connector migration; restore a verified backup.')
