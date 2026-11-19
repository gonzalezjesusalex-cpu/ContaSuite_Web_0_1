"""Catalog additions (3A.5) and confirmed Excel-name equivalences (3A.4) through their explicit migrations."""

import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from test_storage_core import core  # noqa: F401  (fixture)

from app import fiscal_equivalence as eq
from app.fiscal_control import EXTRA, INITIAL, catalog
from app.security import Principal

ADMIN = Principal('test-admin', 'Administrador', True)


def load(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[1] / 'fiscal_migrations' / (name + '.py')
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_catalog_migration_is_idempotent_and_skips_bimestral_rif(core):  # noqa: F811
    sessions = core[1]
    with sessions.kw['bind'].begin() as connection:
        load('001_control_obligaciones').upgrade(connection)
        for _ in range(2):
            load('002_catalogo_excel').upgrade(connection)
    with sessions() as db:
        labels = [row[0] for row in db.execute(select(catalog.c.label))]
        assert len(labels) == len(INITIAL) + len(EXTRA) == len(set(labels))
        assert 'Declaración anual' in labels and 'Expediente físico' in labels
        assert not any('bimestral' in label.casefold() for label in labels)
        annual = db.execute(select(catalog.c.periodicity).where(catalog.c.label == 'Declaración anual')).scalar()
        assert annual == 'annual'
        assert db.scalar(select(func.count()).select_from(catalog)) == 16


def test_equivalences_need_migration_then_confirm_revoke_with_history(core):  # noqa: F811
    sessions = core[1]
    with sessions() as db:
        assert eq.confirmed(db) == {} and eq.listing(db) == []
        with pytest.raises(HTTPException) as unavailable:
            eq.confirm(db, ADMIN, 'ALFA SA', 'company-a')
        assert unavailable.value.status_code == 503
    with sessions.kw['bind'].begin() as connection:
        load('003_equivalencias_excel').upgrade(connection)
    with sessions() as db:
        eq.confirm(db, ADMIN, ' Alfa  SA ', 'company-a')
        assert eq.confirmed(db) == {'alfa sa': 'company-a'}
        row = eq.listing(db)[0]
        assert row['confirmed_by'] == 'test-admin' and row['status'] == 'confirmed' and row['confirmed_at']
        with pytest.raises(HTTPException) as missing:
            eq.confirm(db, ADMIN, 'Otra SA', 'no-existe')
        assert missing.value.status_code == 404
        eq.revoke(db, ADMIN, 'ALFA SA')
        assert eq.confirmed(db) == {}
        with pytest.raises(HTTPException):
            eq.revoke(db, ADMIN, 'ALFA SA')
        eq.confirm(db, ADMIN, 'ALFA SA', 'company-a')  # a revoked name can be confirmed again
        assert eq.confirmed(db) == {'alfa sa': 'company-a'}
        assert [h['action'] for h in eq.trail(db, 'alfa sa')] == ['confirmed', 'revoked', 'confirmed']
