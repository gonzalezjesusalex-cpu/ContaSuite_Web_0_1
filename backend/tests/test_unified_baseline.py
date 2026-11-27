"""Single Alembic chain: unified baseline cs_0006 over the former independent migration chains."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import Session

from test_api import client  # noqa: F401  Isolated environment before app imports.
from app.database import Base
from app.models import Company
from app.schema_compatibility import check_schema
from app.storage.migrate import STORAGE_HEAD, schema_revision, upgrade_schema, upgrade_storage

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
HEAD = 'cs_0025_vault_import_templates'
OLD_CHAIN = [
    ('fiscal_migrations', '001_control_obligaciones'),
    ('credential_migrations', '001_vault'),
    ('import_migrations', '001_reconciliation'),
    ('integral_migrations', '001_integral'),
    ('company_migrations', '001_archive'),
    ('lote4_migrations', '001_lifecycle'),
    ('lote4_migrations', '002_schedule'),
    ('integral_migrations', '002_evidence_history'),
    ('integral_migrations', '003_document_identity'),
]


def local_engine(path):
    engine = create_engine('sqlite:///' + str(path))

    @event.listens_for(engine, 'connect')
    def foreign_keys(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')

    return engine


def old_procedure(engine):
    """What scripts/schema_admin.py --apply did before the unified baseline."""
    upgrade_storage(engine)
    Base.metadata.create_all(engine)
    for folder, name in OLD_CHAIN:
        spec = importlib.util.spec_from_file_location('old' + folder + name, BACKEND / folder / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with engine.begin() as connection:
            module.upgrade(connection)


def snapshot(engine, columns=None):
    """Rows of every table; with `columns`, only those columns (later revisions may add new ones)."""
    with engine.connect() as connection:
        inspector = inspect(connection)
        names = [n for n in inspector.get_table_names() if n != 'alembic_version']
        wanted = columns or {n: [c['name'] for c in inspector.get_columns(n)] for n in names}
        return {
            n: sorted(
                map(
                    tuple,
                    connection.exec_driver_sql(
                        'SELECT ' + ', '.join('"' + c + '"' for c in wanted[n]) + ' FROM "' + n + '"'
                    ).all(),
                ),
                key=repr,
            )
            for n in names
            if n in wanted
        }


def columns_of(engine):
    with engine.connect() as connection:
        inspector = inspect(connection)
        return {n: [c['name'] for c in inspector.get_columns(n)] for n in inspector.get_table_names()}


def test_fresh_database_reaches_single_head_and_is_compatible(tmp_path):
    engine = local_engine(tmp_path / 'fresh.db')
    try:
        assert schema_revision(engine) == (None, HEAD)
        upgrade_schema(engine)
        assert schema_revision(engine) == (HEAD, HEAD)
        assert check_schema(engine)['compatible'], check_schema(engine)['errors']
        with engine.connect() as connection:
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
    finally:
        engine.dispose()


def test_database_prepared_by_old_procedure_upgrades_without_changing_rows(tmp_path):
    engine = local_engine(tmp_path / 'old.db')
    try:
        old_procedure(engine)
        with engine.begin() as db:
            # Raw insert: the current model has columns that this old schema does not have yet.
            db.exec_driver_sql(
                "INSERT INTO companies (id, is_demo, name, rfc, person_type, trade_name, regime, accountant, email, "
                "phone, location, folder, notes, created_at) VALUES ('company-before', 0, 'Sintética', "
                "'AAA010101AA1', 'Moral', '', '601', 'Sin asignar', '', '', '', '', '', CURRENT_TIMESTAMP)"
            )
        assert schema_revision(engine) == (STORAGE_HEAD, HEAD)
        old_columns = columns_of(engine)
        before = snapshot(engine)
        upgrade_schema(engine)
        upgrade_schema(engine)  # idempotent
        assert schema_revision(engine) == (HEAD, HEAD)
        # Existing rows keep every previous value; later revisions only add columns and tables, and the plan v1.1
        # revisions add catalog rows (CSF obligations, password manager portals, office validity per document).
        after = snapshot(engine, old_columns)
        seeded = {'fiscal_catalog', 'vault_services', 'document_validity'}
        for table, rows in before.items():
            if table in seeded:
                assert set(rows) <= set(after[table]), table
            else:
                assert after[table] == rows, table
        assert check_schema(engine)['compatible']
        with Session(engine) as db:
            assert db.scalar(select(Company.name).where(Company.id == 'company-before')) == 'Sintética'
    finally:
        engine.dispose()


def test_schema_admin_status_is_read_only(tmp_path):
    database = tmp_path / 'status.db'
    engine = local_engine(database)
    try:
        old_procedure(engine)
        before = snapshot(engine)
    finally:
        engine.dispose()
    env = {k: v for k, v in os.environ.items() if not k.startswith(('APP_TOKEN', 'AGENT_TOKEN'))}
    env.update(DATABASE_URL='sqlite:///' + str(database), PYTHON_DOTENV_DISABLED='1')
    result = subprocess.run(
        [
            sys.executable,
            '-B',
            str(ROOT / 'scripts' / 'schema_admin.py'),
            '--data-dir',
            str(tmp_path / 'data'),
            '--status',
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    # Since cs_0007 (user roles) an old database needs the explicit update before the application accepts it;
    # --status only reports it.
    assert result.returncode == 1, result.stderr
    assert 'Revision: ' + STORAGE_HEAD + ' (head: ' + HEAD + ') - update pending' in result.stdout
    assert 'Schema incompatible:' in result.stdout and 'user_accounts.role:missing' in result.stdout
    engine = local_engine(database)
    try:
        assert schema_revision(engine) == (STORAGE_HEAD, HEAD)
        assert snapshot(engine) == before
    finally:
        engine.dispose()


def test_status_cannot_be_combined_with_apply(tmp_path):
    env = dict(os.environ, DATABASE_URL='sqlite:///' + str(tmp_path / 'x.db'), PYTHON_DOTENV_DISABLED='1')
    result = subprocess.run(
        [
            sys.executable,
            '-B',
            str(ROOT / 'scripts' / 'schema_admin.py'),
            '--data-dir',
            str(tmp_path / 'data'),
            '--status',
            '--apply',
            '--new',
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2 and 'read-only' in result.stderr
    assert not (tmp_path / 'x.db').exists()
