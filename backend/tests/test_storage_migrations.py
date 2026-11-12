import hashlib
from pathlib import Path
import pytest
from sqlalchemy import create_engine, event, inspect, text, select
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from test_api import client  # Isolated environment before app imports.
from app.models import Base, Company, Document, DocumentVersion, DocumentLocation
from app.storage.migrate import upgrade_storage


def local_engine(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'migration.db'))
    @event.listens_for(engine, 'connect')
    def foreign_keys(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
    return engine


def legacy(engine):
    Company.__table__.create(engine)
    with Session(engine) as db:
        db.add(Company(id='legacy-company', name='Legacy', rfc='AAA010101AA1'))
        db.commit()
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE documents (id VARCHAR(36) PRIMARY KEY, company_id VARCHAR(36) NOT NULL REFERENCES companies(id) ON DELETE CASCADE, name VARCHAR(255) NOT NULL, category VARCHAR(80) NOT NULL, size INTEGER NOT NULL, storage_name VARCHAR(100) NOT NULL, created_at DATETIME NOT NULL)')
        connection.exec_driver_sql("INSERT INTO documents VALUES ('legacy-doc','legacy-company','original.pdf','General',15,'legacy-file.pdf','2026-01-01 12:00:00')")


def test_upgrade_preserves_legacy_ids_bytes_and_unknown_availability(tmp_path):
    engine = local_engine(tmp_path)
    try:
        legacy(engine)
        original = tmp_path / 'legacy-file.pdf'
        original.write_bytes(b'%PDF- unchanged')
        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        upgrade_storage(engine)
        upgrade_storage(engine)
        with Session(engine) as db:
            doc = db.get(Document, 'legacy-doc')
            assert doc.company_id == 'legacy-company' and doc.storage_name == 'legacy-file.pdf'
            assert doc.storage_revision == 1 and not doc.managed
            version = db.scalar(select(DocumentVersion))
            location = db.scalar(select(DocumentLocation))
            assert version.sha256 is None and version.number == 1
            assert location.availability == 'unchecked' and location.last_seen_at is None
            assert len(db.scalars(select(DocumentVersion)).all()) == 1
        with engine.connect() as conn:
            assert conn.exec_driver_sql('PRAGMA foreign_key_check').all() == []
            assert conn.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == 'cs_storage_0004'
            assert conn.exec_driver_sql('SELECT COUNT(*) FROM document_company_links').scalar() == 1
            assert conn.exec_driver_sql('SELECT COUNT(*) FROM storage_events').scalar() == 1
        assert hashlib.sha256(original.read_bytes()).hexdigest() == digest
    finally:
        engine.dispose()


def test_fresh_database_and_frozen_migration_schema_match_models(tmp_path):
    engine = local_engine(tmp_path)
    try:
        upgrade_storage(engine)
        inspector = inspect(engine)
        for name in ('companies', 'documents', 'storage_sources', 'document_versions', 'document_locations',
                     'document_company_links', 'document_classification_reviews', 'storage_index_jobs', 'storage_events',
                     'storage_worker_state', 'identity_state', 'user_accounts', 'user_company_grants', 'user_sessions', 'login_throttles', 'security_events'):
            assert {c.name for c in Base.metadata.tables[name].columns} == {c['name'] for c in inspector.get_columns(name)}, name
        columns = {c['name']: c for c in inspector.get_columns('documents')}
        assert columns['company_id']['nullable'] and columns['storage_name']['nullable']
    finally:
        engine.dispose()


def test_unknown_schema_or_dependencies_fail_without_discarding_data(tmp_path):
    engine = local_engine(tmp_path)
    try:
        legacy(engine)
        with engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE custom_reference (id INTEGER PRIMARY KEY, document_id VARCHAR(36) REFERENCES documents(id) ON DELETE CASCADE)')
            conn.exec_driver_sql("INSERT INTO custom_reference VALUES(1, 'legacy-doc')")
        with pytest.raises(RuntimeError, match='incoming foreign keys'):
            upgrade_storage(engine)
        with engine.connect() as conn:
            assert conn.exec_driver_sql('SELECT COUNT(*) FROM documents').scalar() == 1
            assert conn.exec_driver_sql('SELECT COUNT(*) FROM custom_reference').scalar() == 1
        assert 'managed' not in {c['name'] for c in inspect(engine).get_columns('documents')}
    finally:
        engine.dispose()


def test_postgresql_schema_ddl_compiles_without_network_or_real_server():
    # Dialect compatibility is checked here; this is deliberately NOT a live PostgreSQL migration test.
    for table in Base.metadata.sorted_tables:
        statement = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert 'CREATE TABLE' in statement


def test_identity_upgrade_preserves_block3_catalog_jobs_and_reviews(tmp_path):
    from alembic import command
    from alembic.config import Config
    engine = local_engine(tmp_path)
    try:
        legacy(engine)
        backend = Path(__file__).resolve().parents[1]
        configuration = Config(str(backend/'alembic.ini'))
        configuration.set_main_option('script_location', str(backend/'migrations'))
        with engine.begin() as connection:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            configuration.attributes['connection'] = connection
            command.upgrade(configuration, 'cs_storage_0002')
            connection.exec_driver_sql("INSERT INTO storage_index_jobs(id,source_id,status,requested_by,checkpoint,counters,created_at) VALUES('job-before','cs_legacy','completed','installation_admin','{}','{}','2026-11-01 12:00:00')")
            version_id = connection.exec_driver_sql('SELECT id FROM document_versions').scalar()
            connection.execute(text("INSERT INTO document_classification_reviews(id,document_id,version_id,status,evidence,proposed_links,created_at) VALUES('review-before','legacy-doc',:version,'pending','{}','[]','2026-11-01 12:00:00')"), {'version':version_id})
        tables = ['documents','document_versions','document_locations','document_company_links',
                  'document_classification_reviews','storage_index_jobs','storage_events','storage_sources']
        with engine.connect() as connection:
            before = {name:[tuple(row) for row in connection.exec_driver_sql('SELECT * FROM '+name)] for name in tables}
        upgrade_storage(engine)
        upgrade_storage(engine)
        with engine.connect() as connection:
            after = {name:[tuple(row[:len(before[name][0])]) if before[name] else tuple(row) for row in connection.exec_driver_sql('SELECT * FROM '+name)] for name in tables}
            assert before == after
            assert connection.exec_driver_sql('SELECT COUNT(*) FROM user_accounts').scalar() == 0
            assert not connection.exec_driver_sql('SELECT initialized FROM identity_state').scalar()
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
    finally:
        engine.dispose()
