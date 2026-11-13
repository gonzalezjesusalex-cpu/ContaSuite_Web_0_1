"""Allow the existing completed_with_errors value on PostgreSQL (21 characters)."""
from alembic import op
import sqlalchemy as sa
revision='cs_storage_0005'
down_revision='cs_storage_0004'
branch_labels=None
depends_on=None

def upgrade():
    if op.get_bind().dialect.name=='postgresql':
        op.alter_column('storage_index_jobs','status',existing_type=sa.String(20),type_=sa.String(32),existing_nullable=False)

def downgrade():
    raise RuntimeError('Narrowing status could truncate retained history; no destructive downgrade.')
