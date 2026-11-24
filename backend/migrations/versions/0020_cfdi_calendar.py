"""Plan v1.1, Cambio 3: calendar of the CFDI registered in ContaSuite (cfdi_calendar_entries).

Additive and idempotent: one new, empty table with the header data of each CFDI XML in CS-Storage (issue and
stamping dates, issuer and receiver RFC, type, total). New XML fill it when they enter CS-Storage; the XML
already stored are indexed only when a person asks for it from the calendar («Actualizar calendario»). No
document is read by this revision. Apply only through scripts/schema_admin.py with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0020_cfdi_calendar'
down_revision = 'cs_0019_document_status'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table('cfdi_calendar_entries'):
        return
    op.create_table(
        'cfdi_calendar_entries',
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id'), primary_key=True),
        sa.Column('version_id', sa.String(36), sa.ForeignKey('document_versions.id'), nullable=False),
        sa.Column('uuid', sa.String(36), nullable=True, index=True),
        sa.Column('issued_on', sa.Date(), nullable=False, index=True),
        sa.Column('stamped_on', sa.Date(), nullable=True),
        sa.Column('issuer_rfc', sa.String(13), nullable=False, index=True),
        sa.Column('receiver_rfc', sa.String(13), nullable=False, index=True),
        sa.Column('cfdi_type', sa.String(2), nullable=False),
        sa.Column('total', sa.Numeric(18, 2), nullable=True),
        sa.Column('currency', sa.String(5), nullable=True),
        sa.Column('indexed_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    raise RuntimeError('Retirar el calendario de CFDI sólo quitaría un índice; reconstruirlo exige releer los XML.')
