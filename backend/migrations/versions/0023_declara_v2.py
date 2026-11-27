"""Rediseño de Declara (26/11/2026): ejercicio y modo por análisis, datos de Declara por empresa y bitácora.

Additive and idempotent: nullable columns on declara_runs (ejercicio, modo, carpeta), and three new, empty tables:
declara_company_settings (nombre corto y modo preferido por empresa), declara_folders (carpeta vinculada por empresa y
ejercicio) and declara_log (bitácora: fecha, usuario, equipo, empresa, ejercicio, acción, detalle y ruta). Existing
runs keep NULL in the new columns. Apply only through scripts/schema_admin.py with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0023_declara_v2'
down_revision = 'cs_0022_vault_master_password'
branch_labels = None
depends_on = None

RUN_COLUMNS = [
    ('year', sa.Integer()),
    ('mode', sa.String(10)),
    ('folder_path', sa.String(1000)),
]


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table('declara_runs'):
        existing = {c['name'] for c in inspector.get_columns('declara_runs')}
        for name, kind in RUN_COLUMNS:
            if name not in existing:
                op.add_column('declara_runs', sa.Column(name, kind, nullable=True))
    if not inspector.has_table('declara_company_settings'):
        op.create_table(
            'declara_company_settings',
            sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id'), primary_key=True),
            sa.Column('short_name', sa.String(100), nullable=True),
            sa.Column('mode', sa.String(10), nullable=True),
            sa.Column('updated_by', sa.String(100), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        )
    if not inspector.has_table('declara_folders'):
        op.create_table(
            'declara_folders',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('year', sa.Integer(), nullable=False),
            sa.Column('path', sa.String(1000), nullable=False),
            sa.Column('origin', sa.String(20), nullable=False),
            sa.Column('created_by', sa.String(100), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint('company_id', 'year', name='uq_declara_folders_company_year'),
        )
    if not inspector.has_table('declara_log'):
        op.create_table(
            'declara_log',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column('user_id', sa.String(100), nullable=True),
            sa.Column('user_name', sa.String(150), nullable=True),
            sa.Column('machine', sa.String(100), nullable=True),
            sa.Column('company_id', sa.String(36), nullable=True, index=True),
            sa.Column('year', sa.Integer(), nullable=True),
            sa.Column('run_id', sa.String(36), nullable=True, index=True),
            sa.Column('action', sa.String(60), nullable=False),
            sa.Column('detail', sa.JSON(), nullable=True),
            sa.Column('path', sa.String(1000), nullable=True),
        )


def downgrade():
    raise RuntimeError('Retirar el rediseño de Declara borraría la bitácora y las carpetas vinculadas.')
