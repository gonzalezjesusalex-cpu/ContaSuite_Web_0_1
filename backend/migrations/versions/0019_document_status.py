"""Plan v1.1, Cambio 1: document traffic light (FIEL, CSF, SAT/IMSS opinions, Infonavit).

Additive and idempotent: nullable columns on integral_opinions (folio, source, workers, official validity, issue
time, fields read from the PDF, omitted obligations, review flag) with a unique index on (authority, folio);
two new tables, company_document_settings («No aplica» per company) and document_validity (the office's
validity per document, seeded with the values agreed on 23/11/2026); and nullable company columns (registro
patronal, workers, line of business, REPSE, bank, legal representative). Existing opinions keep NULL in the new
columns. Apply only through scripts/schema_admin.py with a backup.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = 'cs_0019_document_status'
down_revision = 'cs_0018_csf_obligations'
branch_labels = None
depends_on = None

OPINION_COLUMNS = [
    ('folio', sa.String(60)),
    ('source', sa.String(12)),
    ('workers', sa.Integer()),
    ('official_valid_until', sa.Date()),
    ('issued_at', sa.DateTime(timezone=True)),
    ('read_fields', sa.JSON()),
    ('omissions', sa.JSON()),
    ('review', sa.Boolean()),
]
COMPANY_COLUMNS = [
    ('employer_registration', sa.String(20)),
    ('workers', sa.Integer()),
    ('business_activity', sa.String(200)),
    ('repse', sa.Boolean()),
    ('bank', sa.String(100)),
    ('legal_representative', sa.String(200)),
]
# kind: (green up to N days, amber up to M days); past M is red. FIEL counts days left instead of age.
VALIDITY = {'sat': (5, 7), 'csf': (5, 7), 'imss': (0, 1), 'infonavit': (12, 15), 'fiel': (30, 30)}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table('companies'):
        existing = {c['name'] for c in inspector.get_columns('companies')}
        for name, kind in COMPANY_COLUMNS:
            if name not in existing:
                op.add_column('companies', sa.Column(name, kind, nullable=True))
    if not inspector.has_table('integral_opinions'):
        return
    existing = {c['name'] for c in inspector.get_columns('integral_opinions')}
    for name, kind in OPINION_COLUMNS:
        if name not in existing:
            op.add_column('integral_opinions', sa.Column(name, kind, nullable=True))
    if 'uq_integral_opinions_folio' not in {i['name'] for i in inspector.get_indexes('integral_opinions')}:
        op.create_index('uq_integral_opinions_folio', 'integral_opinions', ['authority', 'folio'], unique=True)
    if not inspector.has_table('company_document_settings'):
        op.create_table(
            'company_document_settings',
            sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id'), primary_key=True),
            sa.Column('kind', sa.String(12), primary_key=True),
            sa.Column('not_applicable', sa.Boolean(), nullable=False),
            sa.Column('actor_id', sa.String(100), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        )
    if not inspector.has_table('document_validity'):
        op.create_table(
            'document_validity',
            sa.Column('kind', sa.String(12), primary_key=True),
            sa.Column('green_days', sa.Integer(), nullable=False),
            sa.Column('amber_days', sa.Integer(), nullable=False),
            sa.Column('actor_id', sa.String(100), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        )
    # A new installation may already have the (empty) table from the integral baseline: seed what is missing.
    table = sa.table(
        'document_validity',
        sa.column('kind', sa.String),
        sa.column('green_days', sa.Integer),
        sa.column('amber_days', sa.Integer),
        sa.column('actor_id', sa.String),
        sa.column('updated_at', sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    present = {r[0] for r in bind.execute(sa.select(table.c.kind))}
    stamp = datetime.now(timezone.utc)
    for kind, (green, amber) in VALIDITY.items():
        if kind not in present:
            bind.execute(
                table.insert().values(
                    kind=kind, green_days=green, amber_days=amber, actor_id='migration', updated_at=stamp
                )
            )


def downgrade():
    raise RuntimeError('Retirar el semáforo documental perdería datos leídos de los documentos; sin reversión.')
