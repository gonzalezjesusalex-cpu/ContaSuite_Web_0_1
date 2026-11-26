"""Renovación del gestor de contraseñas, fase 1: master password vault.

Additive and idempotent: two new tables. `vault_config` (one row per installation: data key id, auto-lock minutes)
and `vault_keys` (one wrapped copy of the data key per authorized person and for the recovery code). Both stay empty
here: the vault is created from the screen by an administrator, who then re-wraps the existing envelopes with the
new data key. No secret is created, read or decrypted by this migration. Apply only through scripts/schema_admin.py
with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0022_vault_master_password'
down_revision = 'cs_0021_password_manager'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('vault_credentials'):
        return
    if not inspector.has_table('vault_config'):
        op.create_table(
            'vault_config',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('data_key_id', sa.String(36), nullable=False),
            sa.Column('auto_lock_minutes', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('created_by', sa.String(100), nullable=False),
            sa.Column('migrated', sa.JSON(), nullable=False),
        )
    if not inspector.has_table('vault_keys'):
        op.create_table(
            'vault_keys',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('kind', sa.String(10), nullable=False),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('user_accounts.id'), nullable=True),
            sa.Column('salt', sa.String(64), nullable=False),
            sa.Column('kdf', sa.JSON(), nullable=False),
            sa.Column('wrapped_key', sa.String(200), nullable=False),
            sa.Column('nonce', sa.String(32), nullable=False),
            sa.Column('failed_attempts', sa.Integer(), nullable=False),
            sa.Column('blocked_until', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('created_by', sa.String(100), nullable=False),
            sa.UniqueConstraint('kind', 'user_id'),
        )


def downgrade():
    raise RuntimeError('Retirar la bóveda dejaría los secretos sin llave; sin reversión.')
