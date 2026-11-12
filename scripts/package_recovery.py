"""Deterministic source/runtime ZIP; allowlist excludes configuration, dependencies and data."""
import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def package():
    paths=[]
    for folder in ['backend/app','backend/migrations','backend/fiscal_migrations','backend/credential_migrations','backend/import_migrations','backend/integral_migrations','backend/company_migrations','backend/lote4_migrations','frontend/dist','deploy/windows','docs/qa-recovery']:
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.key'))
    for name in ['backend/requirements-base.txt','backend/requirements.txt','backend/requirements-recovery.lock.txt','backend/alembic.ini','scripts/schema_admin.py','scripts/service_runtime.py','scripts/backup_postgres.py','docs/CS_INTEGRATION_RECOVERY.md','docs/CS_INTEGRATION_RECOVERY_FILES.md','docs/INSTALL_RECOVERY_WINDOWS.md']:
        p=ROOT/name
        if p.is_file():paths.append(p)
    names={p.relative_to(ROOT).as_posix():p for p in paths}
    manifest={name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in sorted(names.items())}
    output=ROOT.parent/'ENTREGAS'/'CS_INTEGRATION_RECOVERY_20261111.zip';output.parent.mkdir(exist_ok=True)
    def build():
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,p in sorted(names.items()):
                info=zipfile.ZipInfo(name,(2026,11,11,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                archive.writestr(info,p.read_bytes())
            info=zipfile.ZipInfo('PACKAGE_SHA256.json',(2026,11,11,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,json.dumps(manifest,sort_keys=True,indent=2).encode())
        return hashlib.sha256(output.read_bytes()).hexdigest()
    first=build();assert first==build(),'Not reproducible'
    with zipfile.ZipFile(output) as archive:
        assert not archive.testzip()
        for name,digest in manifest.items():assert hashlib.sha256(archive.read(name)).hexdigest()==digest
    output.with_suffix('.sha256').write_text(first+'  '+output.name+'\n',encoding='ascii')
    print('Verified reproducible ZIP:',output,'Files:',len(names),'SHA256:',first)
if __name__=='__main__':package()
