"""Validate the authorized import with counts only; no fiscal metadata in diagnostics."""
import sys,json,hashlib,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pilot_first import configuration,RUN,DATABASE
from integration_runtime import BIN,call

def main():
    mode=sys.argv[1];c,env=configuration();access=json.loads((RUN/'access.json').read_text());base=access['url']
    import httpx,psycopg
    from psycopg import sql
    credentials=dict(host='127.0.0.1',port=c['port'],user='pilot_local',password=c['db_password'],connect_timeout=5)
    with httpx.Client(timeout=120) as client:
        assert client.post(base+'/api/auth/login',json={'username':access['username'],'password':access['password']}).status_code==200
        directory=client.get(base+'/api/company-lifecycle?archive=active');assert directory.status_code==200
        assert len(directory.json()['companies'])==1
        dashboard=client.get(base+'/api/integral/dashboard?year=2026&month=11');assert dashboard.status_code==200
        data=dashboard.json();assert data['company_counts']['registered']==1
        assert data['documents']['indexed']>5000
        assert data['obligations']['verified_fulfilled']==0
        catalog=client.get(base+'/api/storage/documents?limit=1');assert catalog.status_code==200
        company_id=directory.json()['companies'][0]['id']
        dossier=client.get(base+'/api/storage/documents',params={'company_id':company_id,'limit':1});assert dossier.status_code==200
    with psycopg.connect(**credentials,dbname=DATABASE) as db:
        assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve()==RUN/'cluster'
        counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['companies','documents','document_versions','document_company_links','fiscal_records','obligations']}
    report={'companies':counts['companies'],'documents':counts['documents'],'versions':counts['document_versions'],
        'links':counts['document_company_links'],'fiscal_records':counts['fiscal_records'],'obligations':counts['obligations'],
        'dashboard_http':200,'directory_http':200,'catalog_http':200,'dossier_http':200,'dashboard_documents':data['documents']['indexed'],
        'associated':data['documents']['associated'],'verified_fulfilled':0}
    if mode=='final':
        os.environ.update(env);sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
        from app.storage.router import storage_service
        from app.storage.service import StorageActor
        from app.storage.connector import ConnectorService
        from app.database import SessionLocal
        from app.models import Company,now
        from app.company_import_models import history,sessions
        from sqlalchemy import select
        from uuid import uuid4
        with SessionLocal.begin() as db:
            company=db.get(Company,company_id)
            if not company.folder:
                company.folder=c['root']
                ident=db.scalar(select(sessions.c.id).where(sessions.c.source=='local_batch'))
                db.execute(history.insert().values(id=str(uuid4()),session_id=ident,actor_id=c['actor'],action='import_folder_linked',created_at=now(),counts={'company_id':company_id,'field':'folder','before':'','after':c['root']}))
        with psycopg.connect(**credentials,dbname=DATABASE) as db:
            sources=db.execute("SELECT id FROM storage_sources WHERE kind='local_folder'").fetchall();assert len(sources)==1
        probe=ConnectorService(storage_service()).probe(StorageActor(c['actor'],admin=True),sources[0][0]);assert probe['state']=='available'
        report['source_available']=True
        imported=json.loads((RUN/'import-summary.json').read_text());assert counts['documents']==imported['imported']==25271
        assert counts['companies']==1 and counts['document_versions']==25271 and counts['fiscal_records']==counts['obligations']==0
        assert data['documents']['indexed']==counts['documents']
        cli=env.copy();cli.update(PGHOST='127.0.0.1',PGPORT=str(c['port']),PGUSER='pilot_local',PGPASSWORD=c['db_password'])
        dump=RUN/'after-authorized-import.dump';call([BIN/'pg_dump.exe','-Fc','--file',dump,DATABASE],cli)
        target='contasuite_pilot_first_import_restore'
        with psycopg.connect(**credentials,dbname='postgres',autocommit=True) as db:
            assert not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(target,)).fetchone()
            db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(target)))
        call([BIN/'pg_restore.exe','--exit-on-error','--dbname',target,dump],cli)
        with psycopg.connect(**credentials,dbname=target) as db:
            restored={t:db.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(t))).fetchone()[0] for t in counts}
        assert counts==restored
        report['backup_sha256']=hashlib.sha256(dump.read_bytes()).hexdigest();report['restored_counts_equal']=True
    (RUN/('import-check-'+mode+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)
if __name__=='__main__':
    try:main()
    except Exception as e:print('Import check stopped; error_class='+type(e).__name__,flush=True);raise SystemExit(1) from None
