"""Plan v1.1, Cambio 4: password manager on the existing vault.

Additive and idempotent: nullable columns on vault_credentials (visible user, portal address, notes, extra data,
holder, strength, keyed fingerprint), vault_certificates.holder (company or legal representative) and
user_sessions.reauth_at (recent password re-entry); two new tables, vault_files (encrypted .cer/.key) and
vault_tickets (one-time tickets for the browser extension, hash only); and the new portals of the catalog.
No secret is created, read or decrypted here. The master keyring is provisioned apart with
scripts/vault_keyring.py (DPAPI) and backed up offline. Apply only through scripts/schema_admin.py with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0021_password_manager'
down_revision = 'cs_0020_cfdi_calendar'
branch_labels = None
depends_on = None

CREDENTIAL_COLUMNS = [
    ('username', sa.String(200)),
    ('url', sa.String(500)),
    ('notes', sa.String(2000)),
    ('extra', sa.JSON()),
    ('holder', sa.String(12)),
    ('strength', sa.Integer()),
    ('fingerprint', sa.String(64)),
]


def add(inspector, table, columns):
    if not inspector.has_table(table):
        return
    existing = {c['name'] for c in inspector.get_columns(table)}
    for name, kind in columns:
        if name not in existing:
            op.add_column(table, sa.Column(name, kind, nullable=True))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    add(inspector, 'user_sessions', [('reauth_at', sa.DateTime(timezone=True))])
    if not inspector.has_table('vault_credentials'):
        return
    add(inspector, 'vault_credentials', CREDENTIAL_COLUMNS)
    add(inspector, 'vault_certificates', [('holder', sa.String(12))])
    if not inspector.has_table('vault_files'):
        op.create_table(
            'vault_files',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('credential_id', sa.String(36), sa.ForeignKey('vault_credentials.id'), nullable=False),
            sa.Column('file_kind', sa.String(10), nullable=False),
            sa.Column('file_name', sa.String(255), nullable=False),
            sa.Column('envelope', sa.JSON(), nullable=False),
            sa.Column('sha256', sa.String(64), nullable=False),
            sa.Column('size', sa.Integer(), nullable=False),
            sa.Column('certificate_id', sa.String(36), nullable=True),
            sa.Column('actor_id', sa.String(100), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )
    if not inspector.has_table('vault_tickets'):
        op.create_table(
            'vault_tickets',
            sa.Column('token_hash', sa.String(64), primary_key=True),
            sa.Column('credential_id', sa.String(36), sa.ForeignKey('vault_credentials.id'), nullable=False),
            sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('actor_id', sa.String(100), nullable=False),
            sa.Column('purpose', sa.String(20), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        )
    from app.credential_models import PORTALS

    services = sa.table('vault_services', sa.column('id', sa.String), sa.column('label', sa.String))
    present = {r[0] for r in bind.execute(sa.select(services.c.id))}
    for key, label in PORTALS.items():
        if key not in present:
            bind.execute(services.insert().values(id=key, label=label))


def downgrade():
    raise RuntimeError('Retirar el gestor de contraseñas perdería secretos cifrados y su bitácora; sin reversión.')
