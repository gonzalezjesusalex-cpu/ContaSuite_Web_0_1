import unittest
from datetime import datetime,timezone,timedelta,date
from sqlalchemy import select
import run_lote4_closure as previous
from app.alert_schedule import metadata,schedule,tick
from app.lote4_summary import summary
from app.lote4_lifecycle import select_certificate,SelectionIn
from app.credential_models import certificates
from app.credential_alerts import candidates

class FinalizationTests(previous.ClosureTests):
    def setUp(self):
        super().setUp();metadata.create_all(previous.previous.previous.harness.engine)
        self.start=datetime(2026,11,11,12,tzinfo=timezone.utc)
        self.db.execute(schedule.insert().values(id=1,next_due=self.start));self.db.commit()
    def test_schedule_one_claim_and_catchup(self):
        calls=[]
        def provider(db,p):calls.append(True);return [self.candidate()]
        self.assertEqual(tick(self.db,lambda:self.start,provider)['state'],'evaluated');self.db.commit()
        self.assertEqual(tick(self.db,lambda:self.start,provider)['state'],'not_due');self.db.commit()
        self.assertEqual(tick(self.db,lambda:self.start+timedelta(days=8),provider)['state'],'evaluated');self.db.commit()
        self.assertEqual(len(calls),2)
    def test_schedule_failure_rolls_back_claim(self):
        def fail(db,p):raise ValueError('synthetic failure')
        with self.assertRaises(ValueError):tick(self.db,lambda:self.start,fail)
        self.db.rollback()
        self.assertEqual(tick(self.db,lambda:self.start,lambda db,p:[])['state'],'evaluated')
    def test_summary_scope_and_archived(self):
        self.save(status='pending',due_date=date(2000,1,1),due_verified=True)
        data=self.read(company_id='a');r=summary(self.db,self.p,{'a'},data['records']);self.assertEqual(r['overdue_obligations'],1)
        self.assertEqual(summary(self.db,self.p,{'b'},[])['overdue_obligations'],0)
        self.archive();self.assertEqual(self.read()['summary']['registered'],0)
    def test_certificate_thresholds_with_clock(self):
        end=self.start+timedelta(days=40)
        self.db.execute(certificates.update().where(certificates.c.id=='old').values(valid_from=self.start-timedelta(days=1),valid_until=end));self.db.commit()
        select_certificate(self.db,self.p,'a',SelectionIn(certificate_id='old',revision=0,reason='selected'))
        for remaining,threshold in [(30,30),(15,15),(7,7)]:
            rows=[r for r in candidates(self.db,self.p,stamp=end-timedelta(days=remaining)) if r['source']=='certificate']
            self.assertEqual(len(rows),1);self.assertTrue(rows[0]['kind'].endswith('_'+str(threshold)))
        self.assertIn('expired',[r['kind'].split('_')[1] for r in candidates(self.db,self.p,stamp=end+timedelta(seconds=1)) if r['source']=='certificate'])
    def test_manual_stale_revision_is_rejected(self):
        from app.lote4_lifecycle import DateIn,save_date
        from fastapi import HTTPException
        self.save();payload=DateIn(company_id='a',obligation_id='m',period_id='2026-11',title='Manual',date=date(2026,11,20),revision=0,reason='initial')
        save_date(self.db,self.p,'stale',payload)
        with self.assertRaises(HTTPException) as error:save_date(self.db,self.p,'stale',payload)
        self.assertEqual(error.exception.status_code,409)
if __name__=='__main__':
    try:unittest.main(verbosity=2)
    finally:previous.previous.previous.harness.engine.dispose()
