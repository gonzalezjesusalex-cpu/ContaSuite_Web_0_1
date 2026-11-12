"""Adopt validated existing core tables, or bootstrap them on a fresh database."""
from alembic import op
import sqlalchemy as sa

revision = 'cs_storage_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table('companies'):
        op.create_table('companies', sa.Column('id', sa.String(36), primary_key=True),
                        sa.Column('is_demo', sa.Boolean(), nullable=False), sa.Column('name', sa.String(220), nullable=False),
                        sa.Column('rfc', sa.String(13), nullable=False), sa.Column('person_type', sa.String(10), nullable=False),
                        sa.Column('trade_name', sa.String(180), nullable=False), sa.Column('regime', sa.String(100), nullable=False),
                        sa.Column('accountant', sa.String(150), nullable=False), sa.Column('email', sa.String(180), nullable=False),
                        sa.Column('phone', sa.String(40), nullable=False), sa.Column('location', sa.String(150), nullable=False),
                        sa.Column('folder', sa.String(1000), nullable=False), sa.Column('notes', sa.Text(), nullable=False),
                        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
        op.create_index('ix_companies_rfc', 'companies', ['rfc'], unique=True)
    else:
        required = {'id', 'rfc', 'name', 'is_demo', 'person_type', 'trade_name', 'regime', 'accountant', 'email', 'phone', 'location', 'folder', 'notes', 'created_at'}
        if not required <= {c['name'] for c in inspector.get_columns('companies')}:
            raise RuntimeError('Incompatible legacy companies schema. Restore or migrate a copy before proceeding.')
    if not inspector.has_table('documents'):
        op.create_table('documents', sa.Column('id', sa.String(36), primary_key=True),
                        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
                        sa.Column('name', sa.String(255), nullable=False), sa.Column('category', sa.String(80), nullable=False),
                        sa.Column('size', sa.Integer(), nullable=False), sa.Column('storage_name', sa.String(100), nullable=False),
                        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
        op.create_index('ix_documents_company_id', 'documents', ['company_id'])
    elif not {'id', 'company_id', 'name', 'category', 'size', 'storage_name', 'created_at'} <= {c['name'] for c in inspector.get_columns('documents')}:
        raise RuntimeError('Incompatible legacy documents schema. No existing document was discarded.')


def downgrade():
    raise RuntimeError('Forward-only migration: never drop existing company/document data. Restore a verified backup instead.')
