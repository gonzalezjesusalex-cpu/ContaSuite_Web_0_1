"""Audit code changes against the verified pre-edit ZIP; never reads operational data/config."""
import json,hashlib,zipfile,difflib,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BACKUP=ROOT.parent/'RESPALDOS'/'CS_INTEGRATION_RECOVERY_20261111'
def ignored(name):return any(p in ('__pycache__','.pytest_cache','node_modules') for p in Path(name).parts) or name.endswith('.pyc')
def main():
    before=json.loads((BACKUP/'baseline.json').read_text(encoding='utf-8'))
    preserved={}
    for folder,name in [('CS_LOTE2_20261111_144333','frontend/tests/lote2.test.mjs'),('CS_LOTE4_FINALIZATION_20261111','frontend/tests/lote4.test.mjs')]:
        historical=json.loads((BACKUP.parent/folder/'final.json').read_text(encoding='utf-8'))
        expected=historical['after'][name]
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected
        preserved[name]=expected
    (BACKUP/'preexisting_verified.json').write_text(json.dumps(preserved,indent=2),encoding='utf-8')
    candidates={n for n in before if not ignored(n)}
    for folder in ['backend','frontend/src','frontend/tests','frontend/dist','scripts','docs','deploy']:
        for parent,dirs,files in os.walk(ROOT/folder):
            dirs[:]=[d for d in dirs if d not in ('__pycache__','.pytest_cache','node_modules')]
            for name in files:
                relative=(Path(parent)/name).relative_to(ROOT).as_posix()
                if not ignored(relative):candidates.add(relative)
    inventory=ROOT/'docs/CS_INTEGRATION_RECOVERY_FILES.md'
    candidates.add(inventory.relative_to(ROOT).as_posix())
    changed={}
    for name in sorted(candidates):
        p=ROOT/name
        digest=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
        if name not in preserved and (digest!=before.get(name) or name==inventory.relative_to(ROOT).as_posix()):
            changed[name]=dict(status='added' if name not in before else 'deleted' if digest is None else 'modified',before=before.get(name),after=digest)
    lines=['# Inventario exacto CS-INTEGRATION-RECOVERY-001','', 'Contra before.zip/baseline.json; omite caches de pruebas y bytecode. Incluye capturas y artefactos compilados.','']
    lines+=['Los dos archivos frontend/tests preexistentes no estaban en el ZIP inicial; no se modificaron y sus SHA-256 se contrastaron con los manifiestos de Lote 2 y FINALIZATION. Véase preexisting_verified.json junto al respaldo.','']
    for status in ('modified','added','deleted'):
        names=[n for n,v in changed.items() if v['status']==status]
        lines.extend([f'## {status} ({len(names)})','',*[f'- `{n}`' for n in names],''])
    inventory.write_text('\n'.join(lines),encoding='utf-8')
    changed[inventory.relative_to(ROOT).as_posix()]['after']=hashlib.sha256(inventory.read_bytes()).hexdigest()
    (BACKUP/'changes.json').write_text(json.dumps(changed,indent=2),encoding='utf-8')
    final={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(candidates) if (ROOT/name).is_file()}
    (BACKUP/'final.json').write_text(json.dumps(final,indent=2),encoding='utf-8')
    diff=[]
    with zipfile.ZipFile(BACKUP/'before.zip') as archive:
        for name,digest in before.items():assert hashlib.sha256(archive.read(name)).hexdigest()==digest
        for name,item in changed.items():
            old=archive.read(name) if item['before'] else b''
            new=(ROOT/name).read_bytes() if item['after'] else b''
            try:
                a=old.decode('utf-8-sig');b=new.decode('utf-8-sig')
                if len(old)+len(new)>250000:diff.append(f'Binary/generated large change: {name}\n');continue
                diff.extend(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='before/'+name,tofile='after/'+name))
            except UnicodeError:diff.append(f'Binary change: {name}\n')
    (BACKUP/'integration.diff').write_text(''.join(diff),encoding='utf-8')
    print('Backup verified. Changed files:',len(changed),'modified:',sum(v['status']=='modified' for v in changed.values()),'added:',sum(v['status']=='added' for v in changed.values()),'deleted:',sum(v['status']=='deleted' for v in changed.values()))
if __name__=='__main__':main()
