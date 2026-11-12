"""Extend the already-tested allowlist package with a private runtime and release installer."""
import hashlib,json,zipfile,argparse
from pathlib import Path
from package_recovery import ROOT
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,required=True);args=parser.parse_args()
    assert (args.runtime/'python312._pth').is_file()
    names={}
    for folder in ['backend/app','backend/migrations','backend/fiscal_migrations','backend/credential_migrations','backend/import_migrations','backend/integral_migrations','backend/company_migrations','backend/lote4_migrations','frontend/dist','deploy/windows','docs/qa-release']:
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.key'):names['app/'+p.relative_to(ROOT).as_posix()]=p
    for name in ['backend/alembic.ini','backend/requirements-recovery.lock.txt','scripts/schema_admin.py','scripts/service_runtime.py','scripts/windows_service.py','scripts/service_admin.py','scripts/backup_postgres.py','scripts/install_release.py','docs/CS_RELEASE_CLOSURE.md','docs/CS_RELEASE_CLOSURE_FILES.md','docs/INSTALL_RELEASE_WINDOWS.md']:
        if (ROOT/name).is_file():names['app/'+name]=ROOT/name
    for p in args.runtime.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:names['runtime/'+p.relative_to(args.runtime).as_posix()]=p
    for name in ['INSTALL.cmd','START.cmd']:names[name]=ROOT/'deploy/windows'/name
    manifest={name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in sorted(names.items())}
    output=ROOT.parent/'ENTREGAS/CS_RELEASE_CLOSURE_20261111.zip'
    def build():
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for name,p in sorted(names.items()):
                info=zipfile.ZipInfo(name,(2026,11,11,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;archive.writestr(info,p.read_bytes())
            info=zipfile.ZipInfo('PACKAGE_SHA256.json',(2026,11,11,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,json.dumps(manifest,sort_keys=True,indent=2).encode())
        return hashlib.sha256(output.read_bytes()).hexdigest()
    digest=build();assert digest==build()
    with zipfile.ZipFile(output) as archive:assert archive.testzip() is None
    output.with_suffix('.sha256').write_text(digest+'  '+output.name+'\n',encoding='ascii')
    print(json.dumps({'file':str(output),'files':len(manifest),'sha256':digest,'bytes':output.stat().st_size}))
if __name__=='__main__':main()
