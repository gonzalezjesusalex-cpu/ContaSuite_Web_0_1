"""Real HTTP + PostgreSQL integration checks with synthetic accounts, no auth overrides."""
import json,sys
from datetime import date
from uuid import uuid4
import httpx
from local_v04 import environment,LAB,API

def main():
    env,engine,values=environment();engine.dispose();checks=[]
    base=f'http://127.0.0.1:{API}'
    def request(c,method,path,expected=200,**kwargs):
        headers={'Origin':base}
        if c.cookies.get('contasuite_csrf'):headers['X-CSRF-Token']=c.cookies.get('contasuite_csrf')
        response=c.request(method,path,headers=headers,**kwargs)
        assert response.status_code==expected,(path,response.status_code)
        if path.startswith('/api/credentials'):assert 'no-store' in response.headers.get('cache-control','')
        return response.json() if response.content else None
    with httpx.Client(base_url=base,timeout=30,trust_env=False) as c:
        request(c,'GET','/api/state',expected=401);checks.append('anonymous_denied')
        request(c,'POST','/api/auth/login',json={'username':'devadmin','password':values['admin_password']})
        state=request(c,'GET','/api/state');assert len(state['companies'])>=4;checks.append('named_admin_authenticated')
        today=date.today();q=f'?year={today.year}&month={today.month}'
        report=request(c,'GET','/api/integral/dashboard'+q);assert report['company_counts']['registered']>=4;checks.append('postgres_dashboard_persisted')
        # Create a fresh synthetic enterprise through the actual API.
        created=request(c,'POST','/api/companies',expected=201,json={'name':'EMPRESA HTTP FICTICIA '+uuid4().hex[:6],'rfc':'TST'+today.strftime('%y%m%d')+uuid4().hex[:3].upper(),'person_type':'Moral','regime':'626 - RESICO','notes':'Registro exclusivamente ficticio para pruebas.'})
        cid=created['id']
        request(c,'PUT','/api/fiscal-control/applicability',json={'company_id':cid,'obligation_id':'fiscal-02','applicable':True,'revision':0})
        body={'company_id':cid,'obligation_id':'fiscal-02','year':today.year,'month':today.month,'revision':0,'status':'pending'}
        cell=request(c,'PUT','/api/fiscal-control/cell',json=body)
        before=request(c,'GET','/api/integral/dashboard'+q+'&company_id='+cid);assert before['obligations']['counts']['pending']==1
        body.update(revision=1,status='in_progress');request(c,'PUT','/api/fiscal-control/cell',json=body)
        after=request(c,'GET','/api/integral/dashboard'+q+'&company_id='+cid);assert after['obligations']['counts']['in_progress']==1
        assert len(request(c,'GET','/api/fiscal-control/history/'+cell['id']))==2;checks.append('companies_obligations_dashboard_history')
        snapshot=request(c,'GET','/api/credentials/companies/lab-company-1');assert not snapshot['reveal_enabled'] and snapshot['certificates'];checks.append('certificates_metadata_only')
        request(c,'POST','/api/credentials/alerts/refresh');a=request(c,'GET','/api/credentials/alerts');request(c,'POST','/api/credentials/alerts/refresh');b=request(c,'GET','/api/credentials/alerts');assert {x['id'] for x in a['alerts']}=={x['id'] for x in b['alerts']};checks.append('alerts_idempotent')
        docs=request(c,'GET','/api/integral/companies/lab-company-2/documents')['documents'];doc=next(d for d in docs if d['name']=='SIN_CLASIFICAR.xml')
        analysis=request(c,'POST','/api/integral/classification/analyze',json={'document_ids':[doc['id']],'reopen':True})
        review=analysis['results'][0]['review_id']
        target=request(c,'GET','/api/fiscal-control'+q)['records'];target=next(r for r in target if r['company_id']=='lab-company-2')
        request(c,'POST',f"/api/integral/classification/documents/{doc['id']}/decision",json={'review_id':review,'revision':doc['revision'],'action':'confirm','company_id':'lab-company-2','category_id':'category-02','year':today.year,'period':f'{today.year}-{today.month:02d}','obligation_id':target['id'],'reason':'Clasificación ficticia de integración HTTP'})
        unchanged=next(r for r in request(c,'GET','/api/fiscal-control'+q)['records'] if r['id']==target['id']);assert unchanged['status']==target['status']
        organized=request(c,'GET','/api/integral/companies/lab-company-2/documents')['documents'];original=request(c,'GET','/api/integral/companies/lab-company-2/documents?original=true')['documents'];assert {d['id'] for d in organized}=={d['id'] for d in original};checks.append('virtual_classification_no_fiscal_state_change')
        content=(LAB/'fixtures'/'obligaciones_FICTICIAS.xlsx').read_bytes()
        preview=request(c,'POST','/api/company-imports/preview/xlsx?source=obligations&synthetic_only=true',content=content)
        assert preview['summary']['total']==2 and preview['summary']['states']['source_duplicate']==1
        request(c,'POST',f"/api/company-imports/{preview['id']}/confirm",expected=423,json={'confirmed':True});checks.append('xlsx_preview_no_final_import')
        request(c,'POST','/api/credentials/companies/lab-company-1/secrets',expected=423,json={'service_id':'sat_password','secret':'Fictional-only-test-secret'});checks.append('vault_locked_no_keys')
    with httpx.Client(base_url=base,timeout=30,trust_env=False) as reader:
        request(reader,'POST','/api/auth/login',json={'username':'devlector','password':values['reader_password']})
        r=request(reader,'GET','/api/integral/dashboard'+q);assert len(r['companies'])==1 and r['companies'][0]['id']=='lab-company-1'
        request(reader,'GET','/api/credentials/companies/lab-company-2',expected=404)
        request(reader,'POST','/api/integral/classification/analyze',expected=403,json={'document_ids':[doc['id']]});checks.append('reader_isolation_permissions')
    report={'database':'contasuite_dev_v04','backend':'http://127.0.0.1:8044','checks':checks,'passed':len(checks),'real_smb_connections':0,'authentication_bypassed':False}
    (LAB/'integration-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        # No response bodies, DSNs, passwords or exception messages are emitted.
        import traceback
        print('Prueba detenida:',type(exc).__name__,'línea',traceback.extract_tb(exc.__traceback__)[-1].lineno);sys.exit(1)
