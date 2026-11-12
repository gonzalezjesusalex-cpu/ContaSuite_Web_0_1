"""Cross-module lifecycle checks using the existing marked synthetic environment."""
import json
import httpx
from integration_runtime import RUN,environment
from integration_http import request,results,BASE
def main():
    config=json.loads((RUN/'synthetic.json').read_text());environment(config)
    with httpx.Client(timeout=30) as client:
        request(client,'POST','/auth/login',json={'username':'recovery_admin','password':'ContaSuite-Sintetica-2026!'})
        matrix=request(client,'GET','/fiscal-control?year=2026&month=11')
        row=matrix['records'][0];cid=row['company_id'];ident=row['id']
        history=request(client,'GET','/integral/obligations/'+ident+'/verifications');initial=len(history);doc=history[-1]['document_id']
        body={k:row[k] for k in ('company_id','obligation_id','revision','status','responsible_id','submitted_at','due_date','due_verified','payment','notes','evidence')}
        body.update(year=2026,month=11,notes='Nueva revisión HTTP sintética')
        request(client,'PUT','/fiscal-control/cell',json=body)
        request(client,'POST','/credentials/alerts/refresh')
        alerts=request(client,'GET','/credentials/alerts?source=obligation&company_id='+cid)
        alert=next(a for a in alerts['alerts'] if a['kind']=='evidence_review')
        report=request(client,'GET','/integral/dashboard?year=2026&month=11&company_id='+cid)
        assert report['lifecycle']['evidence_pending']==1 and report['obligations']['records'][0]['status']=='fulfilled'
        request(client,'PUT','/integral/alerts/'+alert['id']+'/lifecycle',json={'state':'resolved','revision':alert['revision'],'reason':'Revisión documental sin cambio fiscal'})
        request(client,'POST','/credentials/alerts/refresh')
        same=request(client,'GET','/credentials/alerts?company_id='+cid)['alerts'];assert next(a for a in same if a['id']==alert['id'])['state']=='resolved'
        body.update(revision=body['revision']+1,notes='Cambio material HTTP sintético')
        request(client,'PUT','/fiscal-control/cell',json=body);request(client,'POST','/credentials/alerts/refresh')
        reopened=request(client,'GET','/credentials/alerts?company_id='+cid)['alerts'];assert next(a for a in reopened if a['id']==alert['id'])['state']=='pending'
        revision=body['revision']+1
        request(client,'POST','/integral/obligations/'+ident+'/verify',json={'document_id':doc,'revision':revision})
        request(client,'POST','/credentials/alerts/refresh')
        closed=request(client,'GET','/credentials/alerts?company_id='+cid)['alerts'];assert next(a for a in closed if a['id']==alert['id'])['state']=='obsolete'
        history=request(client,'GET','/integral/obligations/'+ident+'/verifications');assert len(history)==initial+1
        app=next((r for r in matrix['applicability'] if r['company_id']==cid and r['obligation_id']=='fiscal-02'),None)
        request(client,'PUT','/fiscal-control/applicability',json={'company_id':cid,'obligation_id':'fiscal-02','applicable':True,'revision':app['revision'] if app else 0})
        before=request(client,'GET','/integral/calendar/management/'+cid)
        manual=next(r for r in before['dates'] if r['id']=='synthetic-manual')
        rule_revision=max((r['version'] for r in before['rules'] if r['id']=='synthetic-rule'),default=0)
        date=dict(company_id=cid,obligation_id='fiscal-02',period_id='2026-11',title='Fecha de revisión sintética',date='2026-11-21',revision=manual['revision'],reason='Edición HTTP con historial')
        request(client,'PUT','/integral/calendar/manual/synthetic-manual',json=date)
        request(client,'PUT','/integral/calendar/manual/synthetic-manual',409,json=date)
        rule={**date,'revision':rule_revision,'source_reference':'Instrucción sintética revisada; sin regla legal general'}
        request(client,'POST','/integral/calendar/rules/synthetic-rule/versions',json=rule)
        request(client,'POST','/integral/calendar/rules/synthetic-rule/versions',json={**rule,'revision':rule_revision+1,'date':'2026-11-22'})
        management=request(client,'GET','/integral/calendar/management/'+cid);assert len(management['rules'])==len(before['rules'])+2 and len(management['history'])==len(before['history'])+3
        request(client,'PUT','/company-lifecycle/'+cid,json={'archived':True,'revision':2})
        default=request(client,'GET','/integral/calendar?anchor=2026-11-11&company_id='+cid);assert default['count']==0
        included=request(client,'GET','/integral/calendar?anchor=2026-11-11&company_id='+cid+'&include_archived=true');assert included['count']>=1
        request(client,'PUT','/company-lifecycle/'+cid,json={'archived':False,'revision':3})
        request(client,'PUT','/fiscal-control/cell',403,headers={'X-CSRF-Token':'invalid-synthetic'},json={**body,'revision':revision})
        report=request(client,'GET','/integral/dashboard?year=2026&month=11&company_id='+cid);assert report['lifecycle']['evidence_pending']==0
        html=client.get(BASE+'/');assert html.status_code==200 and '/assets/index-' in html.text and config['app_token'] not in html.text
    (RUN/'http-followup-results.json').write_text(json.dumps(dict(checks=results,history_before=initial,history_after=len(history),synthetic_only=True),indent=2),encoding='utf-8')
    print('PASS: HTTP followup',len(results),'checks; evidence resolve/reopen/obsolete, dashboard, manual history, rules, archived and CSRF.')
if __name__=='__main__':main()
