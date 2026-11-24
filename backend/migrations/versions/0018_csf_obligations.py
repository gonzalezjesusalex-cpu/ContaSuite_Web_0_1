"""Plan v1.1, Cambio 2: CSF obligations in the Control de obligaciones catalog and per-company dates.

Additive and idempotent: nullable columns on fiscal_catalog (official CSF wording, short name, group, cadence,
regime, due rule and its text, aliases) and on fiscal_applicability (start and end dates, source, wording read on
the constancia), plus the 20 initial CSF obligations. Existing concepts of the internal control keep a NULL group
and are not changed. No company receives obligations here: they are proposed from its CSF and confirmed by a
person. Apply only through scripts/schema_admin.py with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0018_csf_obligations'
down_revision = 'cs_0017_organizador_items'
branch_labels = None
depends_on = None

CATALOG_COLUMNS = [
    ('official_name', sa.String(300)),
    ('short_name', sa.String(60)),
    ('group_name', sa.String(20)),
    ('cadence', sa.String(12)),
    ('regime_scope', sa.String(80)),
    ('due_rule', sa.JSON()),
    ('due_text', sa.String(300)),
    ('aliases', sa.JSON()),
]
APPLICABILITY_COLUMNS = [
    ('start_date', sa.Date()),
    ('end_date', sa.Date()),
    ('source', sa.String(10)),
    ('csf_text', sa.String(300)),
]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table('fiscal_catalog'):
        return
    for table, columns in [('fiscal_catalog', CATALOG_COLUMNS), ('fiscal_applicability', APPLICABILITY_COLUMNS)]:
        existing = {c['name'] for c in inspector.get_columns(table)}
        for name, kind in columns:
            if name not in existing:
                op.add_column(table, sa.Column(name, kind, nullable=True))
    from app.obligation_catalog import ALIASES, INITIAL

    catalog = sa.table(
        'fiscal_catalog',
        sa.column('id', sa.String),
        sa.column('label', sa.String),
        sa.column('periodicity', sa.String),
        sa.column('official_name', sa.String),
        sa.column('short_name', sa.String),
        sa.column('group_name', sa.String),
        sa.column('cadence', sa.String),
        sa.column('regime_scope', sa.String),
        sa.column('due_rule', sa.JSON),
        sa.column('due_text', sa.String),
        sa.column('aliases', sa.JSON),
    )
    ids = {r[0] for r in bind.execute(sa.select(catalog.c.id))}
    labels = {r[0].casefold() for r in bind.execute(sa.select(catalog.c.label))}
    for key, official, short, group, cadence, regime, rule, text in INITIAL:
        if key in ids or short.casefold() in labels:
            continue
        bind.execute(
            catalog.insert().values(
                id=key,
                label=short,
                # The original CHECK allows monthly, quarterly and annual; bimonthly is carried by cadence.
                periodicity='monthly' if cadence == 'bimonthly' else cadence,
                official_name=official,
                short_name=short,
                group_name=group,
                cadence=cadence,
                regime_scope=regime,
                due_rule=rule,
                due_text=text,
                aliases=ALIASES.get(key, []),
            )
        )


def downgrade():
    raise RuntimeError('Retirar el catálogo de obligaciones perdería las casillas marcadas; sin reversión.')
