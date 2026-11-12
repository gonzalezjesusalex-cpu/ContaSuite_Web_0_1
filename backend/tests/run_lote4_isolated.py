import unittest
from datetime import date
import run_lote2_isolated as previous
from app.fiscal_calendar import events,window
from fastapi import HTTPException
class CalendarTests(previous.CompanyTests):
    def test_calendar_confirmed_dates_only(self):
        self.save(status='pending',due_date=date(2026,11,15),due_verified=True)
        self.save(obligation_id='q',due_date=date(2026,11,16),due_verified=False)
        result=events(self.db,previous.harness.ADMIN,date(2026,11,1))
        self.assertEqual(result['count'],1)
        self.assertEqual(result['events'][0]['date'],'2026-11-15')
        self.assertEqual(result['events'][0]['period'],'2026-11')
    def test_calendar_windows(self):
        self.assertEqual(window(date(2024,2,10),'month')[1],date(2024,2,29))
        self.assertEqual(window(date(2026,11,1),'week'),(date(2026,10,26),date(2026,11,1)))
        self.assertEqual(window(date(2026,12,31),'upcoming')[1],date(2027,1,30))
    def test_calendar_scope(self):
        with self.assertRaises(HTTPException):events(self.db,previous.harness.READER,date(2026,11,1),company_id='b')
    def test_calendar_archived_and_idempotent(self):
        self.save(due_date=date(2026,11,15),due_verified=True);self.archive()
        self.assertEqual(events(self.db,previous.harness.ADMIN,date(2026,11,1))['count'],0)
        a=events(self.db,previous.harness.ADMIN,date(2026,11,1),include_archived=True)
        b=events(self.db,previous.harness.ADMIN,date(2026,11,1),include_archived=True)
        self.assertEqual(a,b);self.assertEqual(a['count'],1)
    def test_calendar_read_does_not_change_fiscal(self):
        self.save(status='pending',due_date=date(2026,11,15),due_verified=True)
        before=self.read();events(self.db,previous.harness.ADMIN,date(2026,11,1));self.assertEqual(before,self.read())
if __name__=='__main__':
    try:unittest.main(verbosity=2)
    finally:previous.harness.engine.dispose()
