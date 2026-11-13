"""Unified baseline: brings the former independent chains into the single Alembic history.

Runs, in the fixed order previously applied by scripts/schema_admin.py, the base model tables and the
nine explicit migrations (fiscal, vault, reconciliation, integral, archive, lote4, evidence, identity).
Every step is additive and idempotent, so on a database already prepared by the old procedure this
revision only records the version. The *_migrations/ modules are frozen; new changes go in 0007+.
"""
import importlib.util
from pathlib import Path

from alembic import op

revision = 'cs_0006_unified_baseline'
down_revision = 'cs_storage_0005'
branch_labels = None
depends_on = None

BACKEND = Path(__file__).resolve().parents[2]
LEGACY_CHAIN = [
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


def _load(folder, name):
    spec = importlib.util.spec_from_file_location(folder + name, BACKEND / folder / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade():
    from app import models  # noqa: F401  (registers every table on Base.metadata)
    from app.database import Base

    connection = op.get_bind()
    Base.metadata.create_all(connection)
    for folder, name in LEGACY_CHAIN:
        _load(folder, name).upgrade(connection)


def downgrade():
    raise RuntimeError('Baseline unificada: reversión destructiva deshabilitada; conservar datos e historial.')
