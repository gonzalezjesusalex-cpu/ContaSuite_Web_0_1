"""Data of the Constancia de Situación Fiscal (Bloque 1): new company columns and company_regimes.

Additive and idempotent: nullable columns (idCIF, CURP, fiscal address, start of operations, status in the
taxpayer register, issue date of the constancia) and a new table with every current regime. Existing rows keep
NULL; nothing is inferred. Apply only through scripts/schema_admin.py with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0012_company_csf'
down_revision = 'cs_0011_company_responsible'
branch_labels = None
depends_on = None

COLUMNS = [
    ('idcif', sa.String(11)),
    ('curp', sa.String(18)),
    ('tax_postal_code', sa.String(5)),
    ('tax_street_type', sa.String(80)),
    ('tax_street', sa.String(200)),
    ('tax_exterior_number', sa.String(40)),
    ('tax_interior_number', sa.String(40)),
    ('tax_neighborhood', sa.String(200)),
    ('tax_locality', sa.String(200)),
    ('tax_municipality', sa.String(200)),
    ('tax_state', sa.String(80)),
    ('tax_between_streets', sa.String(300)),
    ('operations_start', sa.Date()),
    ('padron_status', sa.String(40)),
    ('csf_issued_on', sa.Date()),
]


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('companies'):
        return
    existing = {c['name'] for c in inspector.get_columns('companies')}
    for name, kind in COLUMNS:
        if name not in existing:
            op.add_column('companies', sa.Column(name, kind, nullable=True))
    if not inspector.has_table('company_regimes'):
        op.create_table(
            'company_regimes',
            sa.Column(
                'company_id', sa.String(36), sa.ForeignKey('companies.id', ondelete='CASCADE'), primary_key=True
            ),
            sa.Column('position', sa.Integer(), primary_key=True),
            sa.Column('code', sa.String(3), nullable=True),
            sa.Column('label', sa.String(250), nullable=False),
            sa.Column('start_date', sa.Date(), nullable=True),
            sa.Column('end_date', sa.Date(), nullable=True),
        )


def downgrade():
    raise RuntimeError('Retirar los datos de la constancia perdería información capturada; sin reversión.')
