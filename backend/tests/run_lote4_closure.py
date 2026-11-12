import unittest
from datetime import date,timedelta
from sqlalchemy import select,func
from fastapi import HTTPException
import run_lote4_isolated as previous
from app.lote4_lifecycle import *
from app.credential_models import metadata as vault_metadata
from app.fiscal_calendar import events
class ClosureTests(previous.CalendarTests):
    def setUp(self):
        super().setUp();vault_metadata.create_all(previous.previous.harness.engine);metadata.create_all(previous.previous.harness.engine)
        self.p=previous.previous.harness.ADMIN
        for ident,fp in [('old','a'*64),('new','b'*64),('dup','a'*64)]:
            self.db.execute(certificates.insert().values(id=ident,company_id='a',kind='fiel' if ident!='dup' else 'unknown',rfc='AAA010101AA1',fingerprint=fp,origin='manual',reviewed_at=now(),notes='',revision=1))
        self.db.commit()
    def test_renewal_and_explicit_selection(self):
        select_certificate(self.db,self.p,'a',SelectionIn(certificate_id='old',revision=0,reason='review'))
        select_certificate(self.db,self.p,'a',SelectionIn(certificate_id='new',previous_id='old',revision=1,reason='renewal'))
        self.assertEqual(self.db.scalar(select(current.c.certificate_id)),'new')
        self.assertEqual(self.db.scalar(select(renewals.c.previous_id)),'old')
        self.assertEqual(self.db.scalar(select(func.count()).select_from(certificates)),3)
        with self.assertRaises(HTTPException):select_certificate(self.db,self.p,'a',SelectionIn(certificate_id='old',previous_id='new',revision=2,reason='cycle'))
        self.db.rollback()
    def candidate(self,day=date(2026,11,11)):
        return dict(company_id='a',source='obligation',reference='synthetic',kind='overdue',priority='high',due_at=None if day is None else datetime.combine(day,datetime.min.time()))
    def test_alert_states_dedup_snooze_reopen(self):
        evaluate(self.db,self.p,[self.candidate()]);ident=self.db.scalar(select(alerts.c.id))
        count=self.db.scalar(select(func.count()).select_from(history));evaluate(self.db,self.p,[self.candidate()]);self.assertEqual(count,self.db.scalar(select(func.count()).select_from(history)))
        alert_action(self.db,self.p,ident,ActionIn(state='acknowledged',revision=1,reason='reviewed'))
        alert_action(self.db,self.p,ident,ActionIn(state='snoozed',revision=2,reason='later',snooze_until=cutoff()+timedelta(days=5)))
        evaluate(self.db,self.p,[self.candidate()]);self.assertEqual(self.db.scalar(select(alerts.c.state)),'snoozed')
        alert_action(self.db,self.p,ident,ActionIn(state='resolved',revision=3,reason='done'))
        evaluate(self.db,self.p,[self.candidate(date(2026,11,12))]);self.assertEqual(self.db.scalar(select(alerts.c.state)),'pending')
        evaluate(self.db,self.p,[]);self.assertEqual(self.db.scalar(select(alerts.c.state)),'obsolete')
    def test_manual_dates_and_rule_versions(self):
        self.save();from app.fiscal_control import applicability
        self.db.execute(applicability.insert().values(company_id='a',obligation_id='m',applicable=True,updated_at=now(),revision=1));self.db.commit()
        body=dict(company_id='a',obligation_id='m',period_id='2026-11',title='Manual review',date=date(2026,11,20),revision=0,reason='office review')
        save_date(self.db,self.p,'manual',DateIn(**body));self.assertEqual(len([e for e in events(self.db,self.p,date(2026,11,1))['events'] if e['kind']=='manual']),1)
        rule=RuleIn(**body,source_reference='Synthetic reviewed instruction');save_rule(self.db,self.p,'rule',rule)
        save_rule(self.db,self.p,'rule',rule.model_copy(update={'revision':1,'date':date(2026,11,21)}))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(rules)),2)
        with self.assertRaises(HTTPException):save_date(self.db,self.p,'bad',DateIn(**body,rule_id='rule',rule_version=2))
    def test_permissions(self):
        with self.assertRaises(HTTPException):select_certificate(self.db,previous.previous.harness.READER,'a',SelectionIn(certificate_id='old',revision=0,reason='denied'))
    def test_snooze_recovery_and_obsolete_reappearance(self):
        evaluate(self.db,self.p,[self.candidate()]);ident=self.db.scalar(select(alerts.c.id))
        alert_action(self.db,self.p,ident,ActionIn(state='snoozed',revision=1,reason='wait',snooze_until=cutoff()+timedelta(days=1)))
        self.db.execute(update(tracking).where(tracking.c.alert_id==ident).values(snooze_until=cutoff()-timedelta(days=1)));self.db.commit()
        evaluate(self.db,self.p,[self.candidate()]);self.assertEqual(self.db.scalar(select(alerts.c.state)),'pending')
        evaluate(self.db,self.p,[]);evaluate(self.db,self.p,[self.candidate()]);self.assertEqual(self.db.scalar(select(alerts.c.state)),'pending')
    def test_manual_edit_preserves_audit_and_source(self):
        self.save(status='pending')
        body=DateIn(company_id='a',obligation_id='m',period_id='2026-11',title='Review',date=date(2026,11,22),revision=0,reason='initial')
        save_date(self.db,self.p,'edit',body);save_date(self.db,self.p,'edit',body.model_copy(update={'revision':1,'date':date(2026,11,23),'reason':'changed'}))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(history).where(history.c.entity=='calendar')),2)
        self.assertEqual(self.read(company_id='a')['records'][0]['status'],'pending')
if __name__=='__main__':
    try:unittest.main(verbosity=2)
    finally:previous.previous.harness.engine.dispose()
