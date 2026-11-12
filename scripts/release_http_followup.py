import json
import httpx
from release_lab import LAB,configuration
from release_http import BASE,request,checks,xml
def main():
    configuration();fixtures=json.loads((LAB/'fixtures.json').read_text())
    with httpx.Client(timeout=30) as c:
        request(c,'POST','/auth/login',json={'username':'closure_admin','password':'Cierre-Sintetico-2026!'})
        docs=[]
        for cid,total in [(fixtures['a'],'600'),(fixtures['b'],'601')]:
            raw=xml(total).replace(b'12345678-1234-1234-1234-123456789ABC',b'33333333-3333-3333-3333-333333333333')
            docs.append(request(c,'POST','/storage/documents',201,data={'company_id':cid},files={'file':('sin-clasificar.xml',raw,'application/xml')})['id'])
        queue=request(c,'GET','/storage/reconciliation?limit=100')
        assert all(next(r for r in queue['items'] if r['document_id']==ident)['requires_identity_review'] for ident in docs)
        request(c,'POST','/integral/obligations/'+fixtures['record']+'/verify',409,json={'document_id':docs[0],'revision':1})
        before=queue['total'];request(c,'POST','/integral/classification/analyze',json={'document_ids':[docs[0]]})
        after=request(c,'GET','/storage/reconciliation?limit=100');assert after['total']==before
        with httpx.Client(timeout=20) as reader:
            request(reader,'POST','/auth/login',json={'username':'closure_reader','password':'Cierre-Sintetico-2026!'})
            request(reader,'GET','/storage/reconciliation',403)
            request(reader,'GET','/storage/documents/'+docs[1],404)
    (LAB/'http-followup.json').write_text(json.dumps({'checks':checks,'upload_conflicts_before_classification':True,'virtual_queue_not_duplicated':True},indent=2),encoding='utf-8')
    print('PASS: final upload-time identity/queue/verification/permissions HTTP',len(checks))
if __name__=='__main__':main()
