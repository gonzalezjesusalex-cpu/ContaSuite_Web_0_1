"""Named identities and revocable sessions. Frozen additive schema; no document/file changes."""
from alembic import op
import sqlalchemy as sa

revision = 'cs_storage_0003'
down_revision = 'cs_storage_0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('identity_state', sa.Column('id', sa.String(20), primary_key=True),
                    sa.Column('initialized', sa.Boolean(), nullable=False))
    op.create_table('user_accounts', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('username', sa.String(64), nullable=False, unique=True),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('admin', sa.Boolean(), nullable=False), sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('user_company_grants', sa.Column('user_id', sa.String(36), sa.ForeignKey('user_accounts.id'), primary_key=True),
        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id'), primary_key=True),
        sa.Column('access', sa.String(10), nullable=False),
        sa.CheckConstraint("access IN ('read', 'write')", name='ck_user_company_access'))
    op.create_table('user_sessions', sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('user_accounts.id'), nullable=False),
        sa.Column('csrf_hash', sa.String(64), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False), sa.Column('revoked_at', sa.DateTime(timezone=True)))
    op.create_index('ix_user_sessions_user_id', 'user_sessions', ['user_id'])
    op.create_table('login_throttles', sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('attempts', sa.Integer(), nullable=False), sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('security_events', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('actor_id', sa.String(100), nullable=False), sa.Column('action', sa.String(160), nullable=False),
        sa.Column('outcome', sa.String(20), nullable=False), sa.Column('code', sa.String(40)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_security_events_created_at', 'security_events', ['created_at'])
    op.execute(sa.table('identity_state', sa.column('id'), sa.column('initialized')).insert()
               .values(id='identity', initialized=False))


def downgrade():
    raise RuntimeError('Forward-only identity migration. Restore a verified backup to revert.')
