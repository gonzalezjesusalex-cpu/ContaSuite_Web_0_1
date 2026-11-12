import json,sys
import httpx
from release_lab import LAB,configuration
BASE='http://127.0.0.1:8058';checks=[]
def request(client,method,path,status=200,**kw):
    headers={'Origin':BASE,'X-CSRF-Token':client.cookies.get('contasuite_csrf','')};headers.update(kw.pop('headers',{}))
    r=client.request(method,BASE+'/api'+path,headers=headers,**kw)
    assert r.status_code==status,(path,r.status_code,r.text[:400]);checks.append({'method':method,'path':path,'status':r.status_code})
    return r.json() if r.content else None
def xml(total='100'):
    return ('<c:Comprobante xmlns:c="http://www.sat.gob.mx/cfd/4" xmlns:t="http://www.sat.gob.mx/TimbreFiscalDigital" Fecha="2026-11-11T12:00:00" Total="'+total+'"><c:Emisor Rfc="AAA010101AA1"/><c:Receptor Rfc="CCC010101CC1"/><c:Complemento><t:TimbreFiscalDigital UUID="12345678-1234-1234-1234-123456789ABC"/></c:Complemento></c:Comprobante>').encode()
def main():
    config,previous,env=configuration()
    with httpx.Client(timeout=30) as c:
        request(c,'GET','/health')
        request(c,'POST','/auth/bootstrap',201,headers={'Authorization':'Bearer '+config['app_token']},json={'username':'closure_admin','display_name':'Pruebas sintéticas de cierre','password':'Cierre-Sintetico-2026!'})
        request(c,'POST','/auth/login',json={'username':'closure_admin','password':'Cierre-Sintetico-2026!'})
        a=request(c,'POST','/companies',201,json={'name':'CIERRE SINTÉTICO A','rfc':'AAA010101AA1'})['id']
        b=request(c,'POST','/companies',201,json={'name':'CIERRE SINTÉTICO B','rfc':'BBB020202BB2'})['id']
        record=request(c,'PUT','/fiscal-control/cell',json=dict(company_id=a,obligation_id='fiscal-02',year=2026,month=11,revision=0,status='fulfilled'))['id']
        doc=request(c,'POST','/storage/documents',201,data={'company_id':a},files={'file':('original.xml',xml(),'application/xml')})['id']
        request(c,'POST','/storage/documents/'+doc+'/classify')
        request(c,'POST','/integral/obligations/'+record+'/verify',json={'document_id':doc,'revision':1})
        other=request(c,'POST','/storage/documents',201,data={'company_id':b},files={'file':('original.xml',xml('999'),'application/xml')})['id']
        request(c,'POST','/storage/documents/'+other+'/classify')
        queue=request(c,'GET','/storage/reconciliation?limit=1');assert queue['total']==2 and len(queue['items'])==1
        queue=request(c,'GET','/storage/reconciliation?company_id='+a);assert queue['total']==1 and queue['items'][0]['document_id']==doc
        report=request(c,'GET','/integral/dashboard?year=2026&month=11');assert report['obligations']['verified_fulfilled']==0 and report['lifecycle']['evidence_pending']==1
        request(c,'POST','/integral/obligations/'+record+'/verify',409,json={'document_id':doc,'revision':1})
        rid=queue['items'][0]['review_id']
        request(c,'POST','/storage/documents/'+doc+'/reviews/'+rid,422,json={'revision':1,'action':'confirm','links':[]})
        request(c,'POST','/storage/documents/'+doc+'/reviews/'+rid,json={'revision':1,'action':'confirm','links':[],'reason':'Identidad revisada; conservar original independiente'})
        report=request(c,'GET','/integral/dashboard?year=2026&month=11');assert report['obligations']['verified_fulfilled']==0
        request(c,'POST','/integral/obligations/'+record+'/verify',json={'document_id':doc,'revision':1})
        history=request(c,'GET','/integral/obligations/'+record+'/verifications');assert len(history)==2
        request(c,'POST','/credentials/alerts/refresh')
        request(c,'GET','/credentials/alerts?limit=1&state=pending')
        request(c,'PUT','/integral/calendar/manual/closure-manual',json=dict(company_id=a,obligation_id='fiscal-02',period_id='2026-11',title='Revisión documental sintética',date='2026-11-20',revision=0,reason='Agenda interna sintética'))
        request(c,'GET','/integral/calendar?anchor=2026-11-11&view=month')
        request(c,'PUT','/company-lifecycle/'+a,json={'archived':True,'revision':0})
        archived=request(c,'GET','/integral/calendar?anchor=2026-11-11');assert archived['count']==0
        included=request(c,'GET','/integral/calendar?anchor=2026-11-11&include_archived=true');assert included['count']==1
        request(c,'PUT','/company-lifecycle/'+a,json={'archived':False,'revision':1})
        request(c,'POST','/auth/users',201,json={'username':'closure_reader','password':'Cierre-Sintetico-2026!','display_name':'Lector sintético','grants':[{'company_id':a,'access':'read'}]})
        with httpx.Client(timeout=20) as reader:
            request(reader,'POST','/auth/login',json={'username':'closure_reader','password':'Cierre-Sintetico-2026!'})
            request(reader,'GET','/storage/reconciliation',403)
            request(reader,'GET','/storage/documents/'+other,404)
        denied=c.get(BASE+'/api/health',headers={'Host':'unapproved.example'});assert denied.status_code==400
        request(c,'PUT','/fiscal-control/cell',403,headers={'Origin':'https://attacker.example'},json={})
        (LAB/'fixtures.json').write_text(json.dumps({'a':a,'b':b,'doc':doc,'other':other,'record':record}),encoding='utf-8')
    (LAB/'http-results.json').write_text(json.dumps({'checks':checks,'unapproved_host':400,'verification_decisions':2,'synthetic_only':True},indent=2),encoding='utf-8')
    print('Release HTTP passed:',len(checks),'plus unapproved Host; no real services.')
if __name__=='__main__':main()
