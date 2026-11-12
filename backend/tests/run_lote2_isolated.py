"""Standalone synthetic tests. Reuse the verified in-memory, no-network Lote 1 harness."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_lote1_isolated as harness
from sqlalchemy import select, func, create_engine
from sqlalchemy.orm import Session
from fastapi import HTTPException
from pydantic import ValidationError
from app.company_lifecycle import metadata, states, events, set_archive, ArchiveIn, directory, archive_history, ensure_unique_rfc, forbid_delete, available
from app.schemas import CompanyIn
from app.models import Company, Document, Task
from app.security import Principal

class CompanyTests(harness.FiscalReadTests):
    def setUp(self):
        super().setUp()
        metadata.create_all(harness.engine)

    def archive(self, revision=0, archived=True, principal=harness.ADMIN):
        return set_archive('a', ArchiveIn(archived=archived, revision=revision), principal, self.db)

    def test_directory_search_filter_sort(self):
        self.assertEqual(directory(harness.ADMIN,self.db,query='synthetic a')['companies'][0]['id'],'a')
        self.assertEqual([c['id'] for c in directory(harness.ADMIN,self.db,sort='rfc')['companies']],['a','b'])
        self.assertEqual(len(directory(harness.ADMIN,self.db,accountant='Ana')['companies']),1)
        self.archive()
        self.assertEqual([c['id'] for c in directory(harness.ADMIN,self.db)['companies']],['b'])
        self.assertEqual([c['id'] for c in directory(harness.ADMIN,self.db,archive='archived')['companies']],['a'])
        self.assertEqual(len(directory(harness.ADMIN,self.db,archive='all')['companies']),2)

    def test_rfc_normalization_and_self_edit(self):
        value=CompanyIn(name='Synthetic',rfc=' aaa 010101 aa1 ',person_type='Moral')
        self.assertEqual(value.rfc,'AAA010101AA1')
        ensure_unique_rfc(self.db,value.rfc,'a')
        with self.assertRaises(HTTPException) as e:ensure_unique_rfc(self.db,value.rfc)
        self.assertEqual(e.exception.status_code,409)
        with self.assertRaises(ValidationError):CompanyIn(name='Synthetic',rfc='invalid')

    def test_historical_duplicate_flag_no_merge(self):
        self.db.get(Company,'b').rfc=' aaa010101aa1 ';self.db.commit()
        rows=directory(harness.ADMIN,self.db)['companies']
        self.assertEqual(len(rows),2)
        self.assertTrue(all(c['duplicate_rfc'] for c in rows))

    def test_archive_preserves_relations_and_audit(self):
        self.save(status='pending')
        self.db.add(Document(id='d',company_id='a',name='synthetic.xml',category='General',size=1))
        self.db.commit();self.archive();self.archive(1,False)
        self.assertEqual(self.db.get(Document,'d').company_id,'a')
        self.assertEqual(self.db.scalar(select(func.count()).select_from(harness.records)),1)
        rows=archive_history('a',harness.READER,self.db)
        self.assertEqual(len(rows),2)
        self.assertEqual({r['actor_id'] for r in rows},{harness.ADMIN.subject})
        self.assertEqual({r['action'] for r in rows},{'archived','restored'})

    def test_archived_capture_allowed_and_not_restored(self):
        self.archive();self.save(status='fulfilled')
        self.assertTrue(self.db.scalar(select(states.c.archived).where(states.c.company_id=='a')))
        # Global operation excludes archived; direct authorized dossier remains readable.
        self.assertEqual(self.read()['summary']['universe'],3)
        self.assertEqual(self.read(company_id='a')['summary']['registered'],1)

    def test_permissions_and_revoked_principal(self):
        self.assertEqual(len(directory(harness.READER,self.db)['companies']),1)
        with self.assertRaises(HTTPException):self.archive(principal=harness.READER)
        revoked=Principal('revoked','Revoked',False)
        self.assertEqual(directory(revoked,self.db)['companies'],[])
        with self.assertRaises(HTTPException):archive_history('a',revoked,self.db)
        with self.assertRaises(HTTPException):self.read(revoked,company_id='a')

    def test_delete_always_denied(self):
        with self.assertRaises(HTTPException) as e:forbid_delete()
        self.assertEqual(e.exception.status_code,409)
        self.assertIsNotNone(self.db.get(Company,'a'))
        import ast
        source=ast.parse((harness.ROOT/'backend/app/main.py').read_text(encoding='utf-8'))
        endpoint=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='delete_company')
        self.assertEqual(len(endpoint.body),2)
        self.assertEqual(endpoint.body[-1].value.func.id,'forbid_delete')
        self.assertIn('dependencies=ADMIN',ast.unparse(endpoint.decorator_list[0]))

    def test_archive_never_changes_grants_or_fiscal_activity(self):
        from app.models import UserAccount, UserCompanyGrant
        from app.integral_models import activity
        self.db.add(UserAccount(id='writer',username='synthetic_writer',display_name='Writer',password_hash='synthetic-not-a-login',admin=False,enabled=True))
        self.db.flush()
        self.db.add(UserCompanyGrant(user_id='writer',company_id='a',access='write'))
        self.db.execute(activity.insert().values(company_id='a',active=True,actor_id='synthetic',updated_at=harness.now()))
        self.db.commit();self.archive()
        self.assertEqual(self.db.get(UserCompanyGrant,('writer','a')).access,'write')
        self.assertTrue(self.db.scalar(select(activity.c.active).where(activity.c.company_id=='a')))
        writer=Principal('writer','Writer',False,frozenset({'a'}),frozenset({'a'}))
        harness.save_cell(harness.CellIn(company_id='a',obligation_id='m',year=2026,month=11,revision=0),writer,self.db)
        self.assertTrue(self.db.scalar(select(states.c.archived).where(states.c.company_id=='a')))

    def test_archive_revision_conflict(self):
        self.archive()
        with self.assertRaises(HTTPException) as e:self.archive(0,False)
        self.assertEqual(e.exception.status_code,409)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(events)),1)

    def test_lifecycle_missing_schema(self):
        empty=create_engine('sqlite:///:memory:')
        try:
            with Session(empty) as db:
                self.assertFalse(available(db))
                with self.assertRaises(HTTPException) as e:directory(harness.ADMIN,db)
                self.assertEqual(e.exception.status_code,503)
                with self.assertRaises(HTTPException) as e:set_archive('a',ArchiveIn(archived=True,revision=0),harness.ADMIN,db)
                self.assertEqual(e.exception.status_code,503)
        finally:empty.dispose()

if __name__=='__main__':
    try:unittest.main(verbosity=2)
    finally:harness.engine.dispose()
