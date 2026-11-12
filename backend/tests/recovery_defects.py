"""First-run structural regressions; no app import/configuration/connection."""
import ast
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
class Defects(unittest.TestCase):
    def test_startup_no_schema_mutations(self):
        module=ast.parse((ROOT/'backend/app/main.py').read_text(encoding='utf-8'))
        startup=next(n for n in module.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='lifespan')
        for token in ['migrate_receipts(','upgrade_storage(','create_all(']:self.assertFalse(token in ast.unparse(startup),token)
    def test_verification_history_is_recorded(self):
        self.assertTrue('record_verification(' in (ROOT/'backend/app/integral_api.py').read_text(encoding='utf-8'))
    def test_alert_paging_has_authorized_query(self):
        self.assertIn('query_alerts(', (ROOT/'backend/app/credential_alerts.py').read_text(encoding='utf-8'))
    def test_worker_has_independent_modes(self):
        self.assertIn('--mode',(ROOT/'backend/app/storage/worker.py').read_text(encoding='utf-8'))
    def test_calendar_has_visual_grid(self):
        self.assertIn('calendar-grid',(ROOT/'frontend/src/modules/FiscalCalendar.tsx').read_text(encoding='utf-8'))
if __name__=='__main__':unittest.main(verbosity=2)
