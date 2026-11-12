"""Document extensions, storage history and metadata-only adoption of legacy attachments."""
import hashlib
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from alembic import op
import sqlalchemy as sa

revision = 'cs_storage_0002'
down_revision = 'cs_storage_0001'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {c['name']: c for c in sa.inspect(bind).get_columns('documents')}
    additions = [sa.Column('managed', sa.Boolean(), nullable=False, server_default=sa.false()),
                 sa.Column('storage_revision', sa.Integer(), nullable=False, server_default='0'),
                 sa.Column('document_type', sa.String(40), nullable=False, server_default='unknown'),
                 sa.Column('period', sa.String(7), nullable=True),
                 sa.Column('classification_status', sa.String(20), nullable=False, server_default='pending')]
    if any(c.name not in columns for c in additions) or not columns['company_id']['nullable'] or not columns['storage_name']['nullable']:
        if bind.dialect.name == 'sqlite':
            inspector = sa.inspect(bind)
            incoming = [name for name in inspector.get_table_names() if name != 'documents'
                        and any(fk['referred_table'] == 'documents' for fk in inspector.get_foreign_keys(name))]
            if incoming:
                raise RuntimeError('Legacy documents has incoming foreign keys; migrate a verified copy with an explicit dependency plan before rebuilding it.')
        with op.batch_alter_table('documents') as batch:
            for name in ('company_id', 'storage_name'):
                if not columns[name]['nullable']:
                    batch.alter_column(name, existing_type=columns[name]['type'], nullable=True)
            for column in additions:
                if column.name not in columns:
                    batch.add_column(column)
    if 'ix_documents_period' not in {i['name'] for i in sa.inspect(bind).get_indexes('documents')}:
        op.create_index('ix_documents_period', 'documents', ['period'])
    spec = importlib.util.spec_from_file_location('cs_storage_schema_v01', Path(__file__).resolve().parents[1] / 'schema_v01.py')
    snapshot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(snapshot)
    for table in snapshot.Base.metadata.sorted_tables:
        if table.name not in {'companies', 'documents'}:
            table.create(bind, checkfirst=True)
    meta = sa.MetaData()
    meta.reflect(bind)
    sources = meta.tables['storage_sources']
    now = datetime.now(timezone.utc)
    for ident, label, configuration in [('cs_internal', 'Repositorio interno', {}), ('cs_legacy', 'Adjuntos anteriores', {'legacy_read_only': True})]:
        if not bind.execute(sa.select(sources.c.id).where(sources.c.id == ident)).first():
            bind.execute(sources.insert().values(id=ident, label=label, kind='internal', root_path=None, enabled=True, configuration=configuration, created_at=now))
    docs = meta.tables['documents']
    versions = meta.tables['document_versions']
    locations = meta.tables['document_locations']
    links = meta.tables['document_company_links']
    events = meta.tables['storage_events']
    for doc in bind.execute(sa.select(docs).where(docs.c.managed == sa.false(), docs.c.storage_name.isnot(None))).mappings().all():
        if bind.execute(sa.select(versions.c.id).where(versions.c.document_id == doc['id'])).first():
            continue
        def ident(part):
            return str(uuid5(NAMESPACE_URL, 'contasuite:storage:legacy:' + doc['id'] + ':' + part))
        version = ident('version1')
        # Do not open originals during a DB migration or invent fingerprints/availability.
        bind.execute(versions.insert().values(id=version, document_id=doc['id'], number=1, original_name=doc['name'],
                     sha256=None, size=doc['size'], media_type='application/octet-stream', file_metadata={'legacy': True}, created_by='legacy_migration', created_at=doc['created_at']))
        bind.execute(locations.insert().values(id=ident('location'), version_id=version, source_id='cs_legacy',
                     relative_key=doc['storage_name'], key_digest=hashlib.sha256(doc['storage_name'].casefold().encode()).hexdigest(),
                     availability='unchecked', size=doc['size'], mtime_ns=None, last_seen_at=None, error_code=None))
        if doc['company_id']:
            bind.execute(links.insert().values(document_id=doc['id'], company_id=doc['company_id'], role='owner', method='legacy', confirmed_by='legacy_migration', created_at=now))
        bind.execute(docs.update().where(docs.c.id == doc['id']).values(storage_revision=1, classification_status='confirmed' if doc['company_id'] else 'pending'))
        bind.execute(events.insert().values(id=ident('event'), actor_id='legacy_migration', action='legacy_registered', document_id=doc['id'],
                     source_id='cs_legacy', company_id=doc['company_id'], outcome='success', code=None, created_at=now))


def downgrade():
    raise RuntimeError('Forward-only migration: storage history and unclassified documents must be preserved. Restore a verified backup instead.')
