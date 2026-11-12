"""Final reimport against the explicitly synthetic pilot; no bootstrap or real folders."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pilot_http import BASE,USERNAME,PASSWORD,request,review,checks
from pilot_lab import RUN,configuration,original_hashes
from concurrent.futures import ThreadPoolExecutor
import httpx

def main():
    config,previous,env=configuration()
    import psycopg
    credentials=dict(host='127.0.0.1',port=previous['port'],user='recovery_test',password=previous['password'],dbname=config['database'],connect_timeout=5)
    def counts():
        with psycopg.connect(**credentials) as db:
            assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve()==Path(previous['cluster']).resolve()
            return {t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['companies','documents','document_versions','document_company_links','document_classification_reviews','fiscal_records','fiscal_verification_decisions']}
    before=counts()
    with httpx.Client(timeout=120) as c:
        request(c,'POST','/auth/login',json={'username':USERNAME,'password':PASSWORD})
        options=request(c,'GET','/pilot-imports/options');assert len(options['folders'])==2
        data=review(c,request(c,'POST','/pilot-imports/preview',json={'folders':['0','1'],'authorized_read':True}))
        def commit(_):
            with httpx.Client(timeout=120,cookies=c.cookies) as other:
                return request(other,'POST','/pilot-imports/'+data['id']+'/confirm',json={'confirmed':True,'revision':data['summary']['revision']})
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(commit,range(2)))
        assert sum(r['idempotent'] for r in results)==1
        assert request(c,'GET','/storage/reconciliation')['total']==2
    after=counts();assert before==after,(before,after)
    assert original_hashes()==json.loads((RUN/'original-hashes.json').read_text())
    (RUN/'http-final.json').write_text(json.dumps({'synthetic_only':True,'http_checks':len(checks),'counts_unchanged':after,
        'concurrent_confirmation':{'committed':1,'idempotent':1},'source_hashes_unchanged':True,'checks':checks},indent=2),encoding='utf-8')
    print('Final pilot HTTP passed:',len(checks),'checks; documents, reviews and original hashes unchanged.')
if __name__=='__main__':main()
