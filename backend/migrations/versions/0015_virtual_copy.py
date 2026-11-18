"""Internal copy of file contents for the virtual index: virtual_files.copy_sha256 and virtual_files.copied_at.

Additive and idempotent: two nullable columns on an existing table; no row changes and nothing is read from or written
to any document folder by this revision. A file counts as copied while `copy_sha256` equals its current `sha256`.
The copies themselves live outside the database (DATA_DIR/virtual_blobs, named by SHA-256). Apply only through
scripts/schema_admin.py with a backup.
"""

import sqlalchemy as sa
from alembic import op

revision = 'cs_0015_virtual_copy'
down_revision = 'cs_0014_virtual_index'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('virtual_files'):
        return
    columns = {c['name'] for c in inspector.get_columns('virtual_files')}
    if 'copy_sha256' not in columns:
        op.add_column('virtual_files', sa.Column('copy_sha256', sa.String(64), nullable=True))
    if 'copied_at' not in columns:
        op.add_column('virtual_files', sa.Column('copied_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    raise RuntimeError('Retirar el registro de copias dejaría copias sin dueño visible; sin reversión.')
