"""Source backup/diff and anonymized synthetic results; never packages operational data."""
import ast,difflib,hashlib,json,shutil,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    lab=ROOT/'.qa/pilot-import'
    backup=Path((lab/'backup-location.txt').read_text())
    assert backup.parent==ROOT.parent/'RESPALDOS' and backup.name=='CS_PILOT_IMPORT_20261111_180638'
    before=json.loads((backup/'baseline.json').read_text())
    assert digest(backup/'before.zip')=='a7d7dbb6c19a47009d0962addcd3cf00b64720369012daa6e4f7d77b5bca8abb'
    with zipfile.ZipFile(backup/'before.zip') as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read(n)).hexdigest()==value for n,value in before.items())
    dist=ROOT/'frontend/dist'
    bundles=b'\n'.join(p.read_bytes() for p in (dist/'assets').glob('*.js'))
    assert b'/pilot-imports/' in bundles
    hashes={p.relative_to(dist).as_posix():digest(p) for p in sorted(dist.rglob('*')) if p.is_file() and p.name!='contasuite-build.json'}
    (dist/'contasuite-build.json').write_text(json.dumps({'task':'CS-PILOT-IMPORT-001','production_approved':False,
        'schema':'explicit_only','features':['local_pilot_preview','explicit_pilot_confirmation','existing_storage_reviews'],
        'files':hashes},indent=2),encoding='utf-8')
    files=set(before)
    for folder in ['backend','frontend/src','frontend/tests','frontend/dist','scripts','docs']:
        files.update(p.relative_to(ROOT).as_posix() for p in (ROOT/folder).rglob('*') if p.is_file()
                     and not set(p.parts)&{'__pycache__','.pytest_cache','node_modules'} and p.suffix!='.pyc')
    inventory='docs/CS_PILOT_IMPORT_001_FILES.md';files.add(inventory)
    changes={}
    for n in sorted(files):
        value=digest(ROOT/n) if (ROOT/n).is_file() else None
        if value!=before.get(n) or n==inventory:
            changes[n]={'status':'added' if n not in before else 'deleted' if value is None else 'modified','before':before.get(n),'after':value}
    lines=['# Inventario exacto CS-PILOT-IMPORT-001','','Contra before.zip/baseline.json del respaldo CS_PILOT_IMPORT_20261111_180638. Excluye datos, .env, .qa, dependencias, secretos y caches.','']
    for status in ['modified','added','deleted']:
        names=[n for n,v in changes.items() if v['status']==status]
        lines.extend([f'## {status} ({len(names)})','',*[f'- `{n}`' for n in names],''])
    (ROOT/inventory).write_text('\n'.join(lines),encoding='utf-8')
    changes[inventory]['after']=digest(ROOT/inventory)
    after={n:digest(ROOT/n) for n in sorted(files) if (ROOT/n).is_file()}
    for n in changes:
        if n.endswith('.py') and (ROOT/n).is_file():ast.parse((ROOT/n).read_text(encoding='utf-8-sig'),filename=n)
    protected=['backend/app/security.py','backend/app/fiscal_control.py','backend/app/evidence_history.py',
        'backend/app/document_identity.py','backend/app/company_lifecycle.py','backend/app/credential_api.py','backend/app/storage/service.py',
        'backend/app/storage/review.py','backend/app/storage/local.py','backend/app/storage/classifier.py','frontend/src/modules/Companies.tsx']
    assert all(after[n]==before[n] for n in protected)
    (backup/'changes.json').write_text(json.dumps(changes,indent=2),encoding='utf-8')
    (backup/'final.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
    diff=[]
    with zipfile.ZipFile(backup/'before.zip') as z:
        for n,v in changes.items():
            if n.startswith('frontend/dist/') or n.endswith('.jpg'):
                diff.append('Generated/binary change: '+n+'\n');continue
            old=z.read(n).decode('utf-8-sig') if v['before'] else ''
            new=(ROOT/n).read_text(encoding='utf-8-sig') if v['after'] else ''
            diff.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='before/'+n,tofile='after/'+n))
    (backup/'pilot.diff').write_text(''.join(diff),encoding='utf-8')
    results=backup/'results';results.mkdir(exist_ok=True)
    for name in ['all-tests.txt','verified-tests.txt','frontend-final.txt','lab/http-results.json','lab/http-final.json','lab/restore-results.json']:
        shutil.copy2(lab/name,results/Path(name).name)
    http=json.loads((lab/'lab/http-results.json').read_text());last=json.loads((lab/'lab/http-final.json').read_text())
    restored=json.loads((lab/'lab/restore-results.json').read_text())
    assert http['original_hashes_unchanged'] and last['source_hashes_unchanged'] and restored['original_files_unchanged']
    summary={'task':'CS-PILOT-IMPORT-001','synthetic_only':True,'real_folders_accessed':False,'real_import_executed':False,
        'source_backup_sha256':digest(backup/'before.zip'),'changes':{s:sum(v['status']==s for v in changes.values()) for s in ['modified','added','deleted']},
        'general_suite':{'passed':193,'skipped':1,'warnings':161,'note':'Before final targeted corrections; overlapping tests.'},
        'final_affected_suite':{'passed':37,'warnings':27,'pilot_specific':14},'http_initial':40,'http_final':15,
        'typescript_no_emit':'passed','vite_build':'passed; chunk warning >500kB','restore':'passed; new synthetic databases only',
        'visual':'Synthetic form, review, confirmation and result observed; full accessibility/cancel-dialog QA pending',
        'protected_sources_unchanged':protected,'pending':['Two real local-copy paths and explicit authorization to analyse','Human preview and in-app final confirmation for real import','Complete visual/accessibility QA','Operational release acceptance'],
        'v1_approved':False}
    (results/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Verified backup and final inventory:',summary['changes'])
    print('Results:',results)
if __name__=='__main__':main()
