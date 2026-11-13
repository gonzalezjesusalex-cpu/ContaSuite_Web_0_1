"""Ship reproducible source inputs without operational data, real reports or credentials."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT.parent/'ENTREGAS/ContaSuite_v1.0_RC1_fuentes.zip');args=parser.parse_args()
    files={}
    for folder in ['backend/app','backend/tests','backend/migrations','backend/fiscal_migrations','backend/credential_migrations','backend/import_migrations','backend/integral_migrations','backend/company_migrations','backend/lote4_migrations','frontend/src','frontend/tests','frontend/public','deploy/windows']:
        for path in (ROOT/folder).rglob('*'):
            if path.is_file() and not set(path.parts)&{'__pycache__','.pytest_cache','node_modules'} and path.suffix not in {'.pyc','.key','.pem'}:
                files[path.relative_to(ROOT).as_posix()]=path
    for pattern in ['backend/requirements*.txt','backend/alembic.ini','frontend/package*.json','frontend/tsconfig*.json','frontend/vite.config.*','frontend/tailwind.config.*','frontend/postcss.config.*','frontend/index.html']:
        for path in ROOT.glob(pattern):files[path.relative_to(ROOT).as_posix()]=path
    for name in ['schema_admin','service_runtime','windows_service','service_admin','secure_config','backup_postgres','restore_postgres','maintenance_backup','install_release','package_release','package_recovery','package_rc1_sources','build_private_runtime','run_recovery_pytest','release_package_test','release_lab','integration_runtime','rc1_performance']:
        files['scripts/'+name+'.py']=ROOT/'scripts'/(name+'.py')
    for name in ['INSTALL_RC1.md','RC1_VALIDATION.md','INSTALL_RELEASE_WINDOWS.md']:
        files['docs/'+name]=ROOT/'docs'/name
    for name in ['local_setup','local_runtime','local_install','package_local_installer','test_local_installer']:
        files['scripts/'+name+'.py']=ROOT/'scripts'/(name+'.py')
    for name in ['apply_excel_fix','apply_agent','managed_agent','queue_authorized_source','test_agent_package','test_excel_fix']:
        files['scripts/'+name+'.py']=ROOT/'scripts'/(name+'.py')
    files['agent/agent.py']=ROOT/'agent/agent.py'
    files['docs/LOCAL_INSTALLER.txt']=ROOT/'docs/LOCAL_INSTALLER.txt'
    manifest={name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in sorted(files.items())}
    output=args.output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,path in sorted(files.items()):
            info=zipfile.ZipInfo(name,(2026,11,12,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,path.read_bytes())
        info=zipfile.ZipInfo('SOURCE_SHA256.json',(2026,11,12,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
        archive.writestr(info,json.dumps(manifest,indent=2))
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.sha256').write_text(digest+'  '+output.name+'\n',encoding='ascii')
    print(json.dumps({'file':str(output),'files':len(files),'sha256':digest}))
if __name__=='__main__':main()
