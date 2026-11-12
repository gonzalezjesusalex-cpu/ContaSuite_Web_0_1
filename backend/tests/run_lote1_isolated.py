"""Run directly, never through legacy pytest discovery. Synthetic in-memory SQLite only."""
import os
import sys
import tempfile
import socket
import subprocess
import unittest
import ast
import zipfile
import platform
platform.machine = lambda: "AMD64"
platform.win32_ver = lambda: ("10", "10.0", "", "")
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[2]
assert ROOT.name == 'ContaSuite_Web_0_1'
# Explicit recovery reference for this integration; no dependency on the development copy.
assert '--snapshot' in sys.argv, 'Supply --snapshot <verified pre-integration ZIP>'
_arg = sys.argv.index('--snapshot')
SNAPSHOT = Path(sys.argv[_arg + 1]).resolve(strict=True)
del sys.argv[_arg:_arg + 2]
assert SNAPSHOT.suffix == '.zip'
assert SNAPSHOT.parent.parent == ROOT.parent / 'RESPALDOS'
TEMP = tempfile.mkdtemp(prefix='synthetic-', dir=SNAPSHOT.parent)
# Block dotenv at the function boundary, even if the destination has a real .env.
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False
os.environ.update(DATABASE_URL='sqlite:///:memory:', DATA_DIR=TEMP,
                  PYTHON_DOTENV_DISABLED='1', CS_STORAGE_ALLOWED_ROOTS='[]',
                  CS_STORAGE_SMB_ALLOWED_ROOTS='[]', APP_TOKEN='synthetic-only-lote1',
                  AGENT_TOKEN='synthetic-agent-only-lote1', SEED_DEMO='false')
for key in list(os.environ):
    if key.startswith(('VAULT_', 'CS_VAULT_', 'CONTA_VAULT_')):
        os.environ.pop(key)
def forbidden(*args, **kwargs):
    raise AssertionError('Network and external processes forbidden in Lote 1 tests')
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.create_connection = forbidden
class BlockedProcess(subprocess.Popen):
    def __init__(self, *args, **kwargs):
        forbidden()
subprocess.Popen = BlockedProcess
sys.path.insert(0, str(ROOT / 'backend'))
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.database import Base, engine
from app.models import Company, Obligation, Document, DocumentVersion, now
from app.security import Principal
from app.fiscal_control import metadata, catalog, records, history, matrix, save_cell, CellIn
from app.integral_models import metadata as integral_meta, verification
from app.fiscal_read import read_period, indicators
from app.integral_dashboard import dashboard

ADMIN = Principal('synthetic-admin', 'Synthetic', True)
READER = Principal('synthetic-reader', 'Reader', False, frozenset({'a'}))

class FiscalReadTests(unittest.TestCase):
    def setUp(self):
        assert engine.url.render_as_string() == 'sqlite:///:memory:'
        # New synthetic schemas only; no migration entry point or application startup.
        engine.dispose()
        Base.metadata.create_all(engine)
        metadata.create_all(engine)
        integral_meta.create_all(engine)
        self.db = Session(engine)
        self.db.add_all([Company(id='a', name='Synthetic A', rfc='AAA010101AA1', accountant='Ana'),
                         Company(id='b', name='Synthetic B', rfc='BBB010101BB1', accountant='Beto')])
        for ident, frequency in [('m','monthly'),('q','quarterly'),('y','annual')]:
            self.db.execute(catalog.insert().values(id=ident,label=ident,periodicity=frequency))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def save(self, **changes):
        return save_cell(CellIn(**(dict(company_id='a',obligation_id='m',year=2026,month=11,revision=0)|changes)),ADMIN,self.db)

    def read(self, principal=ADMIN, **filters):
        return read_period(self.db,principal,2026,11,**filters)

    def test_implicit_universe(self):
        d=self.read(); self.assertEqual((d['summary']['universe'],d['summary']['implicit']), (6,6))
        self.assertEqual(d['summary']['counts']['unreviewed'],6)

    def test_canonical_and_na(self):
        self.save(status='not_applicable')
        d=self.read();self.assertEqual(d['summary']['counts']['not_applicable'],1)
        self.assertEqual(d['summary']['counts']['unreviewed'],5)

    def test_periods_deduplicated(self):
        self.save(obligation_id='q');self.save(obligation_id='y')
        a=self.read()['cells'];b=read_period(self.db,ADMIN,2026,12)['cells']
        self.assertEqual(indicators(a+b)['universe'],8)

    def test_history_preserved_separately(self):
        self.db.add(Obligation(id='old',company_id='a',title='Legacy',period='2026-11',due_date=date(2000,1,1),status='Presentada',reference='ORIGINAL',notes='x'*5000));self.db.commit()
        self.save(status='fulfilled');d=self.read()
        self.assertEqual(d['summary']['registered'],1)
        self.assertEqual(len(d['historical'][0]['notes']),5000)
        self.assertEqual(d['historical'][0]['reference'],'ORIGINAL')
        self.assertEqual(d['summary']['verified_fulfilled'],0)

    def test_ambiguous_history(self):
        self.db.add(Obligation(id='amb',company_id='a',title='Legacy',period='???',due_date=date(2000,1,1),status='NA'));self.db.commit()
        r=self.read()['historical'][0];self.assertFalse(r['period_reliable']);self.assertIsNone(r['effective_status'])

    def test_scope(self):
        self.assertEqual(self.read(READER)['summary']['universe'],3)
        with self.assertRaises(HTTPException) as e:self.read(READER,company_id='b')
        self.assertEqual(e.exception.status_code,404)

    def test_unverified_date_is_not_overdue(self):
        self.save(status='pending',due_date=date(2000,1,1));self.assertEqual(self.read()['summary']['counts']['overdue'],0)

    def test_verified_date_is_overdue(self):
        self.save(status='pending',due_date=date(2000,1,1),due_verified=True);self.assertEqual(self.read()['summary']['counts']['overdue'],1)

    def test_concurrent_write_and_audit(self):
        self.save()
        with self.assertRaises(HTTPException) as e:self.save(status='fulfilled')
        self.assertEqual(e.exception.status_code,409)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(history)),1)

    def test_reader_cannot_write(self):
        with self.assertRaises(HTTPException):save_cell(CellIn(company_id='a',obligation_id='m',year=2026,month=11,revision=0),READER,self.db)

    def test_legacy_matrix_contract(self):
        self.save();d=matrix(2026,11,ADMIN,self.db)
        self.assertTrue({'companies','catalog','records','applicability','users'}.issubset(d))
        self.assertEqual(d['summary'],self.read()['summary'])

    def test_dashboard_reconciliation(self):
        self.save(status='fulfilled')
        d=dashboard(self.db,ADMIN,2026,11)
        self.assertEqual(d['obligations']['summary'],self.read()['summary'])
        self.assertEqual(d['obligations']['counts']['unreviewed'],5)

    def test_filters_and_report_contract(self):
        self.save(status='pending')
        d=self.read(company_id='a',responsible='Ana',filter_status='pending')
        self.assertEqual(d['summary']['universe'],1)
        self.assertEqual(d['cells'][0]['period_id'],'2026-11')
        self.assertEqual(d['cells'][0]['provenance'],'fiscal_records')
        self.assertIsNone(d['cells'][0]['payment_condition'])

    def test_verified_and_stale_evidence(self):
        ident=self.save(status='fulfilled')['id']
        self.db.add(Document(id='doc',company_id='a',name='synthetic.xml',category='General',size=1,storage_revision=1))
        self.db.flush()
        self.db.add(DocumentVersion(id='v',document_id='doc',number=1,original_name='synthetic.xml',size=1,media_type='application/xml',created_by='synthetic'))
        self.db.flush()
        self.db.execute(verification.insert().values(record_id=ident,record_revision=1,company_id='a',document_id='doc',version_id='v',actor_id='synthetic',verified_at=now()));self.db.commit()
        self.assertEqual(self.read()['summary']['verified_fulfilled'],1)
        self.save(status='fulfilled',revision=1)
        self.assertEqual(self.read()['summary']['verified_fulfilled'],0)

    def test_write_routes_and_sensitive_blocks_unchanged(self):
        with zipfile.ZipFile(SNAPSHOT) as snapshot:
            for rel in ['backend/app/security.py','backend/app/company_import_api.py','backend/app/credential_api.py']:
                self.assertEqual(snapshot.read(rel), (ROOT / rel).read_bytes())
            old=ast.parse(snapshot.read('backend/app/fiscal_control.py'))
            old_main=ast.parse(snapshot.read('backend/app/main.py'))
        current_main=ast.parse((ROOT/'backend/app/main.py').read_text(encoding='utf-8'))
        for name in ['create_obligation','edit_obligation','create_task','edit_task']:
            before=next(n for n in old_main.body if isinstance(n,ast.FunctionDef) and n.name==name)
            after=next(n for n in current_main.body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.dump(before),ast.dump(after))
        current=ast.parse((ROOT/'backend/app/fiscal_control.py').read_text(encoding='utf-8'))
        for name in ['save_cell','save_applicability','changes','add_definition']:
            before=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name==name)
            after=next(n for n in current.body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.dump(before),ast.dump(after))

    def test_current_applicability_does_not_rewrite_history(self):
        from app.fiscal_control import applicability
        self.db.execute(applicability.insert().values(company_id='a',obligation_id='m',applicable=False,revision=1,updated_at=now()))
        self.db.commit()
        cell=next(r for r in self.read()['cells'] if r['company_id']=='a' and r['obligation_id']=='m')
        self.assertFalse(cell['applicability'])
        self.assertEqual(cell['applicability_scope'],'current_configuration')
        self.assertEqual(cell['status'],'unreviewed')

    def test_missing_schema_guard(self):
        from sqlalchemy import create_engine
        empty=create_engine('sqlite:///:memory:')
        try:
            with Session(empty) as db:
                with self.assertRaises(HTTPException) as e:read_period(db,ADMIN,2026,11)
                self.assertEqual(e.exception.status_code,503)
        finally:
            empty.dispose()

if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        engine.dispose()
        pass # Synthetic data directory retained for review; no recursive deletion.
