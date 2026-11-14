"""Local agent linked to the user's session (Bloque 4): agent_links, agent_pair_codes, agent_roots, job attribution.

Additive and idempotent: three new tables and three nullable columns on jobs (who asked, through which link and
from which computer). No agent is linked and no folder is authorized by this revision: an administrator defines
the folders and each user pairs the agent at sign-in. Apply only through scripts/schema_admin.py with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0013_agent_links'
down_revision = 'cs_0012_company_csf'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table('jobs'):
        columns = {c['name'] for c in inspector.get_columns('jobs')}
        for name, kind in [('requested_by', sa.String(36)), ('link_id', sa.String(36)), ('machine', sa.String(120))]:
            if name not in columns:
                op.add_column('jobs', sa.Column(name, kind, nullable=True))
        if 'ix_jobs_requested_by' not in {i['name'] for i in inspector.get_indexes('jobs')}:
            op.create_index('ix_jobs_requested_by', 'jobs', ['requested_by'])
    if not inspector.has_table('agent_links'):
        op.create_table(
            'agent_links',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agent_id', sa.String(80), nullable=False, index=True),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('user_accounts.id'), nullable=False, index=True),
            sa.Column('session_id', sa.String(64), sa.ForeignKey('user_sessions.id'), nullable=False, index=True),
            sa.Column('machine', sa.String(120), nullable=False),
            sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
            sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('revoked_reason', sa.String(120), nullable=True),
            sa.Column('restart_requested', sa.Boolean(), nullable=False),
        )
    if not inspector.has_table('agent_pair_codes'):
        op.create_table(
            'agent_pair_codes',
            sa.Column('code_hash', sa.String(64), primary_key=True),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('user_accounts.id'), nullable=False, index=True),
            sa.Column('session_id', sa.String(64), sa.ForeignKey('user_sessions.id'), nullable=False, index=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        )
    if not inspector.has_table('agent_roots'):
        op.create_table(
            'agent_roots',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('path', sa.String(1000), nullable=False, unique=True),
            sa.Column('created_by', sa.String(36), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )


def downgrade():
    raise RuntimeError('Retirar los vínculos perdería la atribución de los análisis; sin reversión.')
