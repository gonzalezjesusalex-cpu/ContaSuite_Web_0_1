"""Stamp the explicitly authorized integration build without claiming production approval."""
import hashlib,json,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--release',default='CS-INTEGRATION-RECOVERY-001');args=parser.parse_args()
    dist=ROOT/'frontend/dist'
    files={p.relative_to(dist).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dist.rglob('*')) if p.is_file() and p.name!='contasuite-build.json'}
    assert 'index.html' in files
    payload=dict(release=args.release,date='2026-11-11',production_approved=False,
        schemas=['cs_storage_0004','fiscal_0001','vault_0001','integral_0001','company_archive_0001','lote4_lifecycle_0001','lote4_schedule_0002','integral_0002','integral_0003_document_identity'],files=files)
    (dist/'contasuite-build.json').write_text(json.dumps(payload,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print('Integration build files verified:',len(files))
if __name__=='__main__':main()
