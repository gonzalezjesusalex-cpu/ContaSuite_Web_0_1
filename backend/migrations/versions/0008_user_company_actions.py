"""Per-company actions of auxiliar accounts (Bloque 2): user_company_actions(user_id, company_id, action).

Additive and idempotent: creates an empty table. With no rows, an auxiliar keeps what its read/write grant
allowed before roles existed (app/permissions.py). Apply only through scripts/schema_admin.py with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0008_user_company_actions'
down_revision = 'cs_0007_user_role'
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table('user_company_actions'):
        return
    op.create_table(
        'user_company_actions',
        sa.Column('user_id', sa.String(36), sa.ForeignKey('user_accounts.id'), primary_key=True),
        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id'), primary_key=True),
        sa.Column('action', sa.String(40), primary_key=True),
    )


def downgrade():
    raise RuntimeError('Retirar las acciones borraría los permisos concedidos a auxiliares; sin reversión.')
