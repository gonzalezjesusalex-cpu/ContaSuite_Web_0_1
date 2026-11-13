"""End-to-end offline installer test; creates only generated folders and a new cluster."""
import argparse,hashlib,json,os,secrets,subprocess,sys,time,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)

def call(python,code,payload,timeout=240):
    result=subprocess.run([str(python),'-B','-c',code],input=json.dumps(payload),text=True,capture_output=True,timeout=timeout,creationflags=FLAGS)
    if result.returncode:raise RuntimeError('Synthetic installer test subprocess failed:\n'+result.stdout[-1000:]+'\n'+result.stderr[-3000:])
    return result.stdout

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True);args=parser.parse_args()
    assert args.run_id.isalnum()
    work=ROOT/'.qa'/('local-installer-'+args.run_id);work.mkdir(exist_ok=False)
    source=work/'setup';installed=work/'installed'
    archive=ROOT.parent/'ENTREGAS/ContaSuite_Instalador_Pruebas_RC1.zip'
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('PACKAGE_SHA256.json'))
        assert all(hashlib.sha256(z.read(n)).hexdigest()==v for n,v in manifest.items())
        assert not any('.qa' in Path(n).parts or Path(n).name in ('.env','postmaster.pid','PG_VERSION') or n.endswith(('.dump','.key')) for n in manifest)
        z.extractall(source)
    python=source/'runtime/python.exe'
    print(call(python,"import tkinter as tk; root=tk.Tk(); root.withdraw(); root.update(); root.destroy(); print('Tkinter private runtime passed')",{}),flush=True)
    gui="""import sys,tkinter as tk
sys.argv=['local_install.py']
original=tk.Tk.__init__
def initialize(self,*a,**k):
 original(self,*a,**k);self.withdraw()
def inspect(self):
 self.update_idletasks()
 def widgets(w):
  result=[w]
  for child in w.winfo_children():result.extend(widgets(child))
  return result
 items=widgets(self)
 assert sum(w.winfo_class()=='TEntry' for w in items)==5
 assert any(w.winfo_class()=='TScrollbar' for w in items)
 assert any(w.winfo_class()=='TButton' and w.cget('text')=='Instalar ContaSuite de pruebas' for w in items)
 self.destroy();print('Native installer form and scrolling passed')
tk.Tk.__init__=initialize;tk.Tk.mainloop=inspect
from local_install import main
main()
"""
    print(call(python,gui,{}),flush=True)
    fixture=work/'synthetic-company';fixture.mkdir()
    xml=b'<c:Comprobante xmlns:c="http://www.sat.gob.mx/cfd/4" xmlns:t="http://www.sat.gob.mx/TimbreFiscalDigital" Fecha="2026-11-12T12:00:00" Total="100"><c:Emisor Rfc="AAA010101AA1" Nombre="SYNTHETIC INSTALLER"/><c:Receptor Rfc="BBB020202BB2" Nombre="SYNTHETIC COUNTERPARTY"/><c:Complemento><t:TimbreFiscalDigital UUID="11111111-1111-1111-1111-111111111111"/></c:Complemento></c:Comprobante>'
    (fixture/'synthetic.xml').write_bytes(xml)
    from local_setup import free_port
    port=free_port();password=secrets.token_urlsafe(24)
    payload={'source':str(source),'destination':str(installed),'username':'synthetic_admin','password':password,'port':port,'roots':[str(fixture)]}
    code="import json,sys;from pathlib import Path;from local_setup import install;v=json.load(sys.stdin);v['source']=Path(v['source']);v['destination']=Path(v['destination']);print(json.dumps(install(**v,progress=lambda m:print(m,flush=True))))"
    print(call(python,code,payload),flush=True)
    python=installed/'runtime/python.exe'
    started=False
    try:
        print(call(python,"import json,sys;from pathlib import Path;from local_runtime import start;print(json.dumps(start(Path(json.load(sys.stdin)['root']))))",{'root':str(installed)}),flush=True)
        started=True
        import httpx
        url='http://localhost:'+str(port)
        with httpx.Client(base_url=url,timeout=60,trust_env=False) as client:
            assert client.get('/api/state').status_code==401
            response=client.post('/api/auth/login',json={'username':'synthetic_admin','password':password});assert response.status_code==200,response.text
            client.headers.update({'X-CSRF-Token':client.cookies.get('contasuite_csrf'),'Origin':url})
            options=client.get('/api/pilot-imports/options');assert options.status_code==200,options.text
            assert options.json()['mode']=='local' and len(options.json()['folders'])==1
            preview=client.post('/api/pilot-imports/preview',json={'folders':['0'],'authorized_read':True});assert preview.status_code==200,preview.text
            data=preview.json();assert data['summary']['documents']==1
            for row in data['rows']:
                decision={'revision':row['revision'],'reason':'Synthetic installer explicit confirmation'}
                if row['kind']=='company':decision.update(rfc='AAA010101AA1',name='Synthetic installer company')
                else:decision.update(document_type='cfdi',links=[{'folder':'0','role':'issuer'}])
                response=client.put(f"/api/pilot-imports/{data['id']}/rows/{row['number']}",json=decision);assert response.status_code==200,response.text
                data=response.json()
            endpoint='/api/pilot-imports/'+data['id']+'/confirm';body={'revision':data['summary']['revision'],'confirmed':True}
            result=client.post(endpoint,json=body);assert result.status_code==200,result.text
            assert result.json()['documents']==1 and len(result.json()['companies'])==1
            assert client.post(endpoint,json=body).json()['idempotent'] is True
            assert (fixture/'synthetic.xml').read_bytes()==xml
            assert client.get('/tareas?tab=calendario').status_code==200
        print('PASS: login, configured single-folder preview, reviewed import and idempotence',flush=True)
    finally:
        if started:
            print(call(python,"import json,sys;from pathlib import Path;from local_runtime import stop;stop(Path(json.load(sys.stdin)['root']));print('Stopped app and PostgreSQL')",{'root':str(installed)},timeout=120),flush=True)
    # A restart must preserve the confirmed import and the user's account.
    try:
        call(python,"import json,sys;from pathlib import Path;from local_runtime import start;start(Path(json.load(sys.stdin)['root']))",{'root':str(installed)})
        import httpx
        with httpx.Client(base_url=url,timeout=10,trust_env=False) as client:
            assert client.post('/api/auth/login',json={'username':'synthetic_admin','password':password}).status_code==200
            state=client.get('/api/state');assert state.status_code==200 and len(state.json()['companies'])==1
    finally:call(python,"import json,sys;from pathlib import Path;from local_runtime import stop;stop(Path(json.load(sys.stdin)['root']))",{'root':str(installed)},timeout=120)
    result={'synthetic_only':True,'package_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'tkinter':'passed','native_form_and_scrolling':'passed','new_cluster_and_database':'passed','initial_admin_login':'passed','local_import_options':'passed; no pilot-disabled error','one_folder_preview_and_reviewed_confirm':'passed','idempotent_confirmation':'passed','source_unchanged':'passed','restart_data_persistence':'passed','app_and_postgres_stop':'passed','real_folders_read':False,'existing_pilot_modified':False}
    (work/'results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':main()
