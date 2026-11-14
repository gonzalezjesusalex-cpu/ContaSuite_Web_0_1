"""Company change history with its author (Bloque 2): audit_events.actor_id and audit_events.changes.

Additive and idempotent: two nullable columns plus an index. Earlier rows keep NULL (their author was not
recorded). Apply only through scripts/schema_admin.py with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0010_audit_actor'
down_revision = 'cs_0009_run_created_by'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('audit_events'):
        return
    columns = {c['name'] for c in inspector.get_columns('audit_events')}
    if 'actor_id' not in columns:
        op.add_column('audit_events', sa.Column('actor_id', sa.String(100), nullable=True))
    if 'changes' not in columns:
        op.add_column('audit_events', sa.Column('changes', sa.JSON(), nullable=True))
    if 'ix_audit_events_actor_id' not in {i['name'] for i in inspector.get_indexes('audit_events')}:
        op.create_index('ix_audit_events_actor_id', 'audit_events', ['actor_id'])


def downgrade():
    raise RuntimeError('Retirar el autor del historial perdería la trazabilidad; sin reversión.')
