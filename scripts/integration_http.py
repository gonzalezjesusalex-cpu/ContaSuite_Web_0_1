"""Live HTTP against the freshly marked synthetic runtime ONLY."""
import json,sys
from pathlib import Path
import httpx
from integration_runtime import RUN,environment
config=json.loads((RUN/'synthetic.json').read_text());environment(config)
BASE='http://127.0.0.1:8056'
results=[]
def request(client,method,path,expected=200,**kwargs):
    headers={'Origin':BASE,'X-CSRF-Token':client.cookies.get('contasuite_csrf','')};headers.update(kwargs.pop('headers',{}))
    response=client.request(method,BASE+'/api'+path,headers=headers,**kwargs)
    assert response.status_code==expected,(path,response.status_code,response.text[:800])
    results.append(dict(method=method,path=path,status=response.status_code))
    return response.json() if response.content else None
def main():
    password='ContaSuite-Sintetica-2026!'
    with httpx.Client(timeout=30) as client:
        request(client,'GET','/health')
        request(client,'POST','/auth/bootstrap',201,headers={'Authorization':'Bearer '+config['app_token']},json={'username':'recovery_admin','display_name':'Administrador de pruebas sintéticas','password':password})
        request(client,'POST','/auth/login',json={'username':'recovery_admin','password':password})
        a=request(client,'POST','/companies',201,json={'name':'EMPRESA SINTÉTICA RECOVERY A','rfc':'AAA010101AA1'})['id']
        b=request(client,'POST','/companies',201,json={'name':'EMPRESA SINTÉTICA RECOVERY B','rfc':'BBB010101BB1'})['id']
        request(client,'POST','/companies',409,json={'name':'DUPLICADO SINTÉTICO','rfc':' aaa010101aa1 '})
        cell={'company_id':a,'obligation_id':'fiscal-02','year':2026,'month':11,'revision':0,'status':'fulfilled','notes':'Sintético'}
        record=request(client,'PUT','/fiscal-control/cell',json=cell)['id']
        content=b'<Comprobante xmlns="http://www.sat.gob.mx/cfd/4" Fecha="2026-11-11T12:00:00"><Emisor Rfc="AAA010101AA1"/><Receptor Rfc="BBB010101BB1"/></Comprobante>'
        doc=request(client,'POST','/storage/documents',201,data={'company_id':a},files={'file':('synthetic.xml',content,'application/xml')})['id']
        payload={'document_id':doc,'revision':1}
        request(client,'POST','/integral/obligations/'+record+'/verify',json=payload)
        repeat=request(client,'POST','/integral/obligations/'+record+'/verify',json=payload);assert repeat['idempotent']
        cell.update(revision=1,notes='Segunda revisión sintética');request(client,'PUT','/fiscal-control/cell',json=cell)
        request(client,'POST','/integral/obligations/'+record+'/verify',json={'document_id':doc,'revision':2})
        history=request(client,'GET','/integral/obligations/'+record+'/verifications');assert len(history)==2
        request(client,'PUT','/company-lifecycle/'+a,json={'archived':True,'revision':0})
        request(client,'GET','/company-lifecycle?archive=archived')
        request(client,'PUT','/company-lifecycle/'+a,json={'archived':False,'revision':1})
        request(client,'DELETE','/companies/'+a,409)
        date=request(client,'PUT','/integral/calendar/manual/synthetic-manual',json={'company_id':a,'obligation_id':'fiscal-02','period_id':'2026-11','title':'Revisión interna sintética','date':'2026-11-20','revision':0,'reason':'HTTP aislado'})
        request(client,'GET','/integral/calendar?anchor=2026-11-11&view=month')
        request(client,'POST','/credentials/alerts/refresh')
        request(client,'GET','/credentials/alerts?limit=20&state=pending')
        request(client,'GET','/integral/dashboard?year=2026&month=11')
        reader=request(client,'POST','/auth/users',201,json={'username':'recovery_reader','password':password,'display_name':'Lector sintético','grants':[{'company_id':a,'access':'read'}]})
        with httpx.Client(timeout=30) as limited:
            request(limited,'POST','/auth/login',json={'username':'recovery_reader','password':password})
            state=request(limited,'GET','/state');assert {c['id'] for c in state['companies']}=={a}
            request(limited,'GET','/integral/calendar?anchor=2026-11-11&company_id='+b,404)
            request(limited,'PUT','/fiscal-control/cell',404,json={**cell,'revision':2})
            request(limited,'POST','/companies',403,json={'name':'No permitido','rfc':'CCC010101CC1'})
            request(client,'PUT','/auth/users/'+reader['id'],json={'display_name':'Lector revocado','enabled':True,'admin':False,'revision':reader['revision'],'grants':[]})
            request(limited,'GET','/state',401)
        (RUN/'http-results.json').write_text(json.dumps({'checks':results,'verification_decisions':len(history),'synthetic_only':True},indent=2),encoding='utf-8')
        (RUN/'ui-test-account.json').write_text(json.dumps({'username':'recovery_admin','password':password,'synthetic':True}),encoding='utf-8')
        print('HTTP checks passed:',len(results),'Preserved verification decisions:',len(history))
if __name__=='__main__':main()
