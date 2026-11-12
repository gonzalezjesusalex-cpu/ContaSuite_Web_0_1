import json
import httpx
from release_lab import LAB,configuration
from release_http import BASE,request,checks
def main():
    configuration();f=json.loads((LAB/'fixtures.json').read_text())
    with httpx.Client(timeout=30) as c:
        request(c,'POST','/auth/login',json={'username':'closure_admin','password':'Cierre-Sintetico-2026!'})
        queue=request(c,'GET','/storage/reconciliation?company_id='+f['a']);item=queue['items'][0]
        doc=item['document_id'];rid=item['review_id'];version=item['version']
        request(c,'POST','/storage/documents/'+doc+'/reviews/'+rid,json={'revision':version,'action':'reject','links':[],'reason':'Rechazo sintético para ensayar corrección'})
        one=request(c,'POST','/storage/documents/'+doc+'/reviews/'+rid+'/reopen',json={'revision':version,'reason':'Revisar rechazo humano sintético'})
        repeat=request(c,'POST','/storage/documents/'+doc+'/reviews/'+rid+'/reopen',json={'revision':version,'reason':'Reintento idempotente sintético'})
        assert one['review_id']==repeat['review_id'] and repeat['idempotent']
        request(c,'POST','/storage/documents/'+doc+'/reviews/'+one['review_id'],json={'revision':version,'action':'correct','links':[{'company_id':f['a'],'role':'owner'}],'reason':'Conservar vínculo independiente tras reapertura'})
        rows=request(c,'GET','/storage/documents/'+doc+'/reviews')
        assert next(r for r in rows if r['id']==rid)['resolution']=='reject'
        assert next(r for r in rows if r['id']==one['review_id'])['resolution']=='correct'
        history=request(c,'GET','/integral/obligations/'+f['record']+'/verifications');assert len(history)==2
    (LAB/'http-reopen.json').write_text(json.dumps({'checks':checks,'previous_rejection_preserved':True,'idempotent':True,'fiscal_history_unchanged':True},indent=2),encoding='utf-8')
    print('PASS: HTTP explicit reopen',len(checks),'checks; rejection/fiscal history preserved')
if __name__=='__main__':main()
