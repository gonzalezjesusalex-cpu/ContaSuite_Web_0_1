"""Record hashes after an explicitly authorized frontend build. Does not build or package."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path


def stamp(root):
    dist=root/'frontend'/'dist'
    bundles=b'\n'.join(p.read_bytes() for p in (dist/'assets').glob('*.js'))
    for marker in [b'/auth/bootstrap',b'/storage/connector/sources',b'/storage/dashboard']:
        if marker not in bundles:
            raise RuntimeError('The compiled frontend does not contain all required visit features.')
    files={p.relative_to(dist).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(dist.rglob('*')) if p.is_file() and p.name!='contasuite-build.json'}
    payload={'built_at':datetime.now(timezone.utc).isoformat(),'schema':'cs_storage_0004',
             'features':['named_sessions','storage_connector','certificate_dashboard'],'files':files}
    (dist/'contasuite-build.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    return len(files)


if __name__=='__main__':
    print('Frontend verificado:',stamp(Path(__file__).resolve().parents[1]),'archivos con SHA-256.')
