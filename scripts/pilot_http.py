"""Exercise actual HTTP with synthetic folders exclusively; diagnostics contain no document metadata."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pilot_lab import RUN,configuration,original_hashes
import httpx
from concurrent.futures import ThreadPoolExecutor

BASE='http://127.0.0.1:8060'
USERNAME='pilot_synthetic_admin';PASSWORD='Piloto-Sintetico-2026!'
checks=[]

def request(c,method,path,status=200,**kw):
    headers={'Origin':BASE,'X-CSRF-Token':c.cookies.get('contasuite_csrf','')};headers.update(kw.pop('headers',{}))
    r=c.request(method,BASE+'/api'+path,headers=headers,**kw)
    assert r.status_code==status,(path,r.status_code,r.text[:250])
    checks.append({'method':method,'route':path.split('?')[0],'status':status})
    return r.json() if r.content else None

def review(c,data):
    for row in data['rows']:
        payload={'revision':row['revision'],'reason':'Revisión humana de fixture sintético, sin validación fiscal'}
        if row['kind']=='company':payload.update(rfc='AAA010101AA1' if row['folder']=='0' else 'BBB020202BB2',name='PILOTO SINTETICO '+row['folder'])
        else:
            payload.update(document_type=row['type'],include=not bool(row['error']),links=([{'folder':'0','role':'issuer'},{'folder':'1','role':'receiver'}] if row['type']=='cfdi' else [{'folder':row['folder'],'role':'owner'}]))
        data=request(c,'PUT',f"/pilot-imports/{data['id']}/rows/{row['number']}",json=payload)
    return data

def main():
    config,previous,env=configuration()
    with httpx.Client(timeout=120) as c:
        request(c,'GET','/pilot-imports/options',401)
        request(c,'POST','/auth/bootstrap',201,headers={'Authorization':'Bearer '+config['app_token']},json={'username':USERNAME,'display_name':'Piloto sintético','password':PASSWORD})
        request(c,'POST','/auth/login',json={'username':USERNAME,'password':PASSWORD})
        opts=request(c,'GET','/pilot-imports/options');assert len(opts['folders'])==2
        request(c,'POST','/pilot-imports/preview',422,json={'folders':['0','1'],'authorized_read':False})
        data=request(c,'POST','/pilot-imports/preview',json={'folders':['0','1'],'authorized_read':True})
        assert data['summary']['documents']==7 and data['summary']['conflicts']==2
        assert sum(bool(r.get('duplicate')) for r in data['rows'])==2
        assert sum(bool(r.get('error')) for r in data['rows'])==1
        assert all(not r['rfc'] for r in data['rows'] if r['kind']=='company')
        state=request(c,'GET','/state');assert not state['companies'] and not state['documents']
        data=review(c,data)
        request(c,'POST','/pilot-imports/'+data['id']+'/confirm',422,json={'confirmed':False,'revision':data['summary']['revision']})
        request(c,'POST','/pilot-imports/'+data['id']+'/confirm',409,json={'confirmed':True,'revision':0})
        # Two concurrent confirmations of one reviewed snapshot yield one commit.
        def commit(_):
            with httpx.Client(timeout=120,cookies=c.cookies) as other:
                return request(other,'POST','/pilot-imports/'+data['id']+'/confirm',json={'confirmed':True,'revision':data['summary']['revision']})
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(commit,range(2)))
        assert sum(r['idempotent'] for r in results)==1
        first=results[0];assert first['documents']==6 and first['pending']==2
        state=request(c,'GET','/state');assert len(state['companies'])==2
        queue=request(c,'GET','/storage/reconciliation');assert queue['total']==2
        # Reanalyse/reconfirm through a new session: no company/document/version duplication.
        again=review(c,request(c,'POST','/pilot-imports/preview',json={'folders':['0','1'],'authorized_read':True}))
        request(c,'POST','/pilot-imports/'+again['id']+'/confirm',json={'confirmed':True,'revision':again['summary']['revision']})
        request(c,'DELETE','/company-imports/'+data['id'],404)
        request(c,'GET','/pilot-imports')
        request(c,'POST','/auth/users',201,json={'username':'pilot_synthetic_reader','password':PASSWORD,'display_name':'Lector sintético','grants':[{'company_id':first['companies'][0],'access':'read'}]})
        with httpx.Client(timeout=20) as reader:
            request(reader,'POST','/auth/login',json={'username':'pilot_synthetic_reader','password':PASSWORD})
            request(reader,'GET','/pilot-imports/options',403)
            request(reader,'GET','/pilot-imports/'+data['id'],403)
            request(reader,'POST','/pilot-imports/'+data['id']+'/confirm',403,json={'confirmed':True,'revision':data['summary']['revision']})
        assert c.get(BASE+'/api/pilot-imports/options').headers.get('cache-control')=='no-store, private'
    assert original_hashes()==json.loads((RUN/'original-hashes.json').read_text())
    import psycopg
    with psycopg.connect(host='127.0.0.1',port=previous['port'],user='recovery_test',password=previous['password'],dbname=config['database']) as db:
        assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve()==Path(previous['cluster']).resolve()
        counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['companies','documents','document_versions','document_company_links','fiscal_records','obligations']}
        assert counts=={'companies':2,'documents':6,'document_versions':6,'document_company_links':6,'fiscal_records':0,'obligations':0},counts
    report={'synthetic_only':True,'checks':checks,'http_checks':len(checks),'detected_companies':2,'analysed_documents':7,
        'imported_documents':6,'pending_conflicts':2,'unreadable_content':1,'unsupported_files':1,'shared_duplicate_documents':2,
        'excluded_entries':3,'original_hashes_unchanged':True,'counts_after_reimport':counts,'concurrent_confirmation':{'committed':1,'idempotent':1}}
    (RUN/'http-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Pilot HTTP passed:',len(checks),'checks; original synthetic file hashes unchanged.')
if __name__=='__main__':main()
