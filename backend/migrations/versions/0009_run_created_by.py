"""Who created each Recopila, CFDI and Declara run and each receipt (Bloque 2, point 2b): `created_by`.

Additive and idempotent: a nullable column plus its index. Existing rows keep NULL (their author was never
recorded); without a company they stay visible to administrators only. Apply only through
scripts/schema_admin.py with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0009_run_created_by'
down_revision = 'cs_0008_user_company_actions'
branch_labels = None
depends_on = None

TABLES = ('receipts', 'recopila_runs', 'organizador_runs', 'declara_runs')


def upgrade():
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        if not inspector.has_table(table):
            continue
        if 'created_by' not in {c['name'] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column('created_by', sa.String(100), nullable=True))
        index = 'ix_' + table + '_created_by'
        if index not in {i['name'] for i in inspector.get_indexes(table)}:
            op.create_index(index, table, ['created_by'])


def downgrade():
    raise RuntimeError('Retirar el autor de las ejecuciones cambiaría quién puede verlas; sin reversión.')
