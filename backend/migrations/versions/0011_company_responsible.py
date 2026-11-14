"""Responsible accountant by user id (Bloque 2): companies.accountant_id and companies.accountant_legacy.

Additive and idempotent. The free text in `accountant` is copied to `accountant_legacy` (except the default
"Sin asignar") and nothing is assigned: matching names to accounts is a human review in the application
(app/responsible.py), never automatic. Apply only through scripts/schema_admin.py with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0011_company_responsible'
down_revision = 'cs_0010_audit_actor'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('companies'):
        return
    columns = {c['name'] for c in inspector.get_columns('companies')}
    if 'accountant_id' not in columns:
        op.add_column('companies', sa.Column('accountant_id', sa.String(36), nullable=True))
    if 'accountant_legacy' not in columns:
        op.add_column('companies', sa.Column('accountant_legacy', sa.String(150), nullable=True))
        op.execute(
            "UPDATE companies SET accountant_legacy = accountant "
            "WHERE accountant IS NOT NULL AND TRIM(accountant) <> '' AND accountant <> 'Sin asignar'"
        )
    if 'ix_companies_accountant_id' not in {i['name'] for i in inspector.get_indexes('companies')}:
        op.create_index('ix_companies_accountant_id', 'companies', ['accountant_id'])


def downgrade():
    raise RuntimeError('Retirar el vínculo con el responsable perdería las asignaciones; sin reversión.')
