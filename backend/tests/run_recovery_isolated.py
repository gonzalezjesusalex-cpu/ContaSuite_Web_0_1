import unittest,hashlib,asyncio
from datetime import datetime,timezone
from io import BytesIO
from contextlib import contextmanager
from types import SimpleNamespace
from sqlalchemy import select,func,event,inspect
import run_lote4_finalization as previous
from app.evidence_history import metadata,decisions
from app.models import Document,DocumentVersion
from app.integral_api import verify,VerifyIn
from app.security import Principal
from app.alert_query import query_alerts
from app.credential_models import alerts
from app.storage.worker import run_once
class RecoveryTests(previous.FinalizationTests):
    def setUp(self):
        super().setUp();metadata.create_all(previous.previous.previous.previous.harness.engine)
    def test_repeated_verification_keeps_history_and_is_idempotent(self):
        ident=self.save(status='fulfilled')['id'];raw=b'synthetic evidence'
        self.db.add(Document(id='ev',company_id='a',name='synthetic.xml',category='General',size=len(raw),storage_revision=1))
        self.db.flush();self.db.add(DocumentVersion(id='ev1',document_id='ev',number=1,original_name='synthetic.xml',sha256=hashlib.sha256(raw).hexdigest(),size=len(raw),media_type='application/xml',created_by='synthetic'));self.db.commit()
        import app.storage.router as storage_router
        original=storage_router.storage_service
        class Fake:
            @contextmanager
            def read(self,*args):yield SimpleNamespace(stream=BytesIO(raw))
        storage_router.storage_service=lambda:Fake()
        try:
            first=verify(ident,VerifyIn(revision=1,document_id='ev'),self.p,self.db)
            again=verify(ident,VerifyIn(revision=1,document_id='ev'),self.p,self.db)
            self.assertEqual(first['decision_id'],again['decision_id']);self.assertTrue(again['idempotent'])
            other=Principal('second-reviewer','Second reviewer',True)
            verify(ident,VerifyIn(revision=1,document_id='ev'),other,self.db)
            self.assertEqual(self.db.scalar(select(func.count()).select_from(decisions)),2)
            correction=verify(ident,VerifyIn(revision=1,document_id='ev'),self.p,self.db)
            self.assertFalse(correction['idempotent'])
            self.assertTrue(verify(ident,VerifyIn(revision=1,document_id='ev'),self.p,self.db)['idempotent'])
            self.assertEqual(self.db.scalar(select(func.count()).select_from(decisions)),3)
            from app.integral_models import audit
            self.assertEqual(set(self.db.scalars(select(audit.c.company_id).where(audit.c.action=='compliance_evidence_verified'))),{'a'})
            self.db.get(Document,'ev').storage_revision=2;self.db.commit()
            self.assertEqual(self.read(company_id='a')['summary']['verified_fulfilled'],0)
            self.assertEqual(self.db.scalar(select(func.count()).select_from(decisions)),3)
        finally:storage_router.storage_service=original
    def test_alert_authorization_before_pagination_over_1000(self):
        stamp=datetime.now(timezone.utc)
        self.db.execute(alerts.insert(),[dict(id=str(i).zfill(64),company_id='b' if i<1100 else 'a',source='obligation',reference=str(i),kind='pending',priority='high',generated_at=stamp,state='pending') for i in range(1205)]);self.db.commit()
        reader=previous.previous.previous.previous.harness.READER
        first=query_alerts(self.db,reader,limit=50,state='pending')
        second=query_alerts(self.db,reader,offset=50,limit=50,state='pending')
        self.assertEqual(first['total'],105);self.assertEqual(len(first['alerts']),50)
        self.assertTrue(all(r['company_id']=='a' for r in first['alerts']+second['alerts']))
        self.assertFalse({r['id'] for r in first['alerts']} & {r['id'] for r in second['alerts']})
    def test_alert_mode_never_indexes(self):
        class Forbidden:
            def tick(self,*args):raise AssertionError('Index side effect')
        calls=[];run_once('alerts',Forbidden(),lambda:calls.append(1));self.assertEqual(calls,[1])
    def test_evidence_alerts_follow_history_without_changing_fiscal_status(self):
        from app.credential_alerts import candidates
        from app.lote4_lifecycle import evaluate,alert_action,ActionIn,tracking
        from app.fiscal_control import records
        from sqlalchemy import update
        ident=self.save(status='fulfilled')['id']
        source=lambda:[r for r in candidates(self.db,self.p) if r['kind']=='evidence_review']
        self.assertEqual(len(source()),1)
        evaluate(self.db,self.p,source());first=self.db.execute(select(alerts)).mappings().one()
        alert_action(self.db,self.p,first['id'],ActionIn(state='resolved',revision=1,reason='review pending'))
        evaluate(self.db,self.p,source());self.assertEqual(self.db.scalar(select(alerts.c.state)),'resolved')
        self.db.execute(update(records).where(records.c.id==ident).values(revision=2));self.db.commit()
        evaluate(self.db,self.p,source());self.assertEqual(self.db.scalar(select(alerts.c.state)),'pending')
        self.assertEqual(self.db.scalar(select(records.c.status).where(records.c.id==ident)),'fulfilled')
        self.assertEqual(query_alerts(self.db,self.p)['total'],1)
    def test_startup_does_not_change_schema(self):
        from app.database import engine
        from app.schema_compatibility import metadatas
        for m in metadatas():m.create_all(engine)
        before=set(inspect(engine).get_table_names())
        from app.main import lifespan
        def no_ddl(conn,cursor,statement,*args):
            self.assertFalse(statement.lstrip().split()[0].upper() in ('CREATE','ALTER','DROP'))
        event.listen(engine,'before_cursor_execute',no_ddl)
        try:
            context=lifespan(None)
            # Startup has synchronous inspection/work only; drive its coroutine without a socket-based event loop.
            for operation in [context.__aenter__(),context.__aexit__(None,None,None)]:
                try:operation.send(None)
                except StopIteration:pass
                else:raise AssertionError('Unexpected asynchronous IO in startup test')
        finally:event.remove(engine,'before_cursor_execute',no_ddl)
        self.assertEqual(before,set(inspect(engine).get_table_names()))
if __name__=='__main__':
    try:unittest.main(verbosity=2)
    finally:previous.previous.previous.previous.harness.engine.dispose()
