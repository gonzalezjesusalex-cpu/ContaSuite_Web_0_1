"""Managed agent and backed-up full-folder queue, on generated data only."""
import argparse,hashlib,json,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='final');args=parser.parse_args();assert args.run_id.isalnum()
    work=ROOT/'.qa'/('agent-package-'+args.run_id);work.mkdir(exist_ok=False)
    setup=work/'setup';archive=ROOT.parent/'ENTREGAS/ContaSuite_RC1_Agente_Windows.zip'
    with zipfile.ZipFile(archive) as z:
        hashes=json.loads(z.read('PACKAGE_SHA256.json'));assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in hashes.items());z.extractall(setup)
    target=ROOT/'.qa/local-installer-final/installed'
    assert target.is_relative_to(ROOT/'.qa')
    fixture=work/'authorized-fixture';fixture.mkdir();(fixture/'safe.xml').write_text('<Comprobante/>');(fixture/'password.xml').write_text('SYNTHETIC EXCLUDED')
    payload={'setup':str(setup),'target':str(target),'fixture':str(fixture)}
    code="""import sys,json,time,subprocess
from pathlib import Path
from apply_excel_fix import apply
from apply_agent import FILES
from local_runtime import start,stop
from local_setup import marker
from secure_config import load
from sqlalchemy import create_engine,text
v=json.load(sys.stdin);root=Path(v['target']);source=Path(v['setup']);marker(root)
apply(source,root,FILES);start(root)
def query(statement,parameters=None):
 engine=create_engine(load(root/'private/service.json')['DATABASE_URL'])
 try:
  with engine.begin() as db:
   result=db.execute(text(statement),parameters or {});return result.all() if result.returns_rows else []
 finally:engine.dispose()
try:
 for _ in range(30):
  agents=query("SELECT id FROM agents WHERE id LIKE 'windows-%'")
  if agents:break
  time.sleep(.5)
 assert agents,'Managed agent did not connect'
 prepare="import json,sys;from pathlib import Path;from queue_authorized_source import prepare;v=json.load(sys.stdin);print(json.dumps(prepare(Path(v['target']),Path(v['fixture']))))"
 result=subprocess.run([str(source/'runtime/python.exe'),'-B','-c',prepare],input=json.dumps(v),text=True,capture_output=True,timeout=180)
 assert result.returncode==0,result.stderr
 report=json.loads(result.stdout);job=report['job_id']
 for _ in range(120):
  state=query('SELECT status,counters FROM storage_index_jobs WHERE id=:id',{'id':job})
  if state and state[0][0] not in ('queued','running'):break
  time.sleep(.5)
 assert state[0][0]=='completed',str(state)
 assert state[0][1]['new']==1 and (Path(report['backup'])/'database.dump').is_file()
 query("UPDATE storage_index_jobs SET status='completed_with_errors' WHERE id=:id",{'id':job})
 assert query('SELECT status FROM storage_index_jobs WHERE id=:id',{'id':job})[0][0]=='completed_with_errors'
 query("UPDATE storage_index_jobs SET status='completed' WHERE id=:id",{'id':job})
 assert (Path(v['fixture'])/'safe.xml').read_text()=='<Comprobante/>'
 # Exercise actual agent HTTP claim and delivery with one newly authorized job.
 from uuid import uuid4
 agent=agents[0][0];company=query('SELECT id,folder FROM companies LIMIT 1')[0];job_id=str(uuid4())
 query('UPDATE companies SET folder=:folder WHERE id=:id',{'folder':v['fixture'],'id':company[0]})
 query("INSERT INTO jobs(id,company_id,agent_id,kind,status,payload,result,created_at) VALUES(:id,:company,:agent,'scan_folder','queued',CAST(:payload AS json),CAST('{}' AS json),CURRENT_TIMESTAMP)",{'id':job_id,'company':company[0],'agent':agent,'payload':json.dumps({'folder':v['fixture']})})
 for _ in range(40):
  inventory=query('SELECT status,result FROM jobs WHERE id=:id',{'id':job_id})[0]
  if inventory[0] in ('completed','failed'):break
  time.sleep(.5)
 assert inventory[0]=='completed' and [f['name'] for f in inventory[1]['files']]==['safe.xml'],str(inventory[0])
 query('UPDATE companies SET folder=:folder WHERE id=:id',{'folder':company[1],'id':company[0]})
 print(json.dumps({'agent_connected':True,'agent_inventory_delivered':True,'backup_created':True,'document_queue_completed':True,'secret_excluded':True,'source_unchanged':True}))
finally:stop(root)
"""
    result=subprocess.run([str(setup/'runtime/python.exe'),'-B','-c',code],input=json.dumps(payload),text=True,capture_output=True,timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
    print(result.stdout)
    (work/'results.json').write_text(json.dumps({'synthetic_only':True,'package_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'agent_and_full_folder_queue':'passed'},indent=2))
if __name__=='__main__':main()
