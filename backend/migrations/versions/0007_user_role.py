"""User roles (Bloque 2): user_accounts.role = admin | contador | auxiliar.

Additive and idempotent. Existing administrators become `admin`; any other existing account becomes `auxiliar`
and keeps its per-company read/write grants (decision of 14/11/2026, docs/BLOQUE_2_ROLES.md). The `admin`
boolean is kept in step with the role. On a fresh database the baseline already creates the column from the
model, so this revision only records the version. Apply only through scripts/schema_admin.py with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0007_user_role'
down_revision = 'cs_0006_unified_baseline'
branch_labels = None
depends_on = None

ROLE_CHECK = "role IN ('admin', 'contador', 'auxiliar')"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c['name'] for c in inspector.get_columns('user_accounts')}
    if 'role' not in columns:
        op.add_column('user_accounts', sa.Column('role', sa.String(20), nullable=False, server_default='auxiliar'))
        op.execute("UPDATE user_accounts SET role = CASE WHEN admin THEN 'admin' ELSE 'auxiliar' END")
    checks = {c['name'] for c in inspector.get_check_constraints('user_accounts')}
    # SQLite cannot add a constraint to an existing table and is test-only; there the ORM validates the value.
    if bind.dialect.name == 'postgresql' and 'ck_user_account_role' not in checks:
        op.create_check_constraint('ck_user_account_role', 'user_accounts', ROLE_CHECK)


def downgrade():
    raise RuntimeError('Retirar los roles perdería la asignación de contadores y auxiliares; sin reversión.')
