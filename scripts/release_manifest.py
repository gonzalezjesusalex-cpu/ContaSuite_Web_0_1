"""Exact release source diff, excluding operational configuration and data."""
import os,json,zipfile,hashlib,difflib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BACKUP=ROOT.parent/'RESPALDOS/CS_RELEASE_CLOSURE_20261111_225752'
def main():
    before=json.loads((BACKUP/'baseline.json').read_text());names=set(before)
    for folder in ['backend','frontend/src','frontend/tests','frontend/dist','frontend/public','scripts','docs','deploy']:
        for parent,dirs,files in os.walk(ROOT/folder):
            dirs[:]=[d for d in dirs if d not in ('__pycache__','.pytest_cache','node_modules')]
            for f in files:
                if not f.endswith('.pyc'):names.add((Path(parent)/f).relative_to(ROOT).as_posix())
    inventory='docs/CS_RELEASE_CLOSURE_FILES.md';names.add(inventory);changes={}
    for name in sorted(names):
        p=ROOT/name;digest=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
        if digest!=before.get(name) or name==inventory:changes[name]={'status':'added' if name not in before else 'deleted' if digest is None else 'modified','before':before.get(name),'after':digest}
    lines=['# Inventario exacto CS-RELEASE-CLOSURE-001','','Contra before.zip/baseline.json del respaldo CS_RELEASE_CLOSURE_20261111_225752. Excluye .qa, datos/configuración, dependencias, caches y bytecode.','']
    for status in ['modified','added','deleted']:
        rows=[n for n,v in changes.items() if v['status']==status]
        lines.extend([f'## {status} ({len(rows)})','',*[f'- `{n}`' for n in rows],''])
    (ROOT/inventory).write_text('\n'.join(lines),encoding='utf-8');changes[inventory]['after']=hashlib.sha256((ROOT/inventory).read_bytes()).hexdigest()
    after={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names) if (ROOT/n).is_file()}
    (BACKUP/'changes.json').write_text(json.dumps(changes,indent=2),encoding='utf-8');(BACKUP/'final.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
    diff=[]
    with zipfile.ZipFile(BACKUP/'before.zip') as archive:
        for name,digest in before.items():assert hashlib.sha256(archive.read(name)).hexdigest()==digest
        for name,v in changes.items():
            old=archive.read(name) if v['before'] else b'';new=(ROOT/name).read_bytes() if v['after'] else b''
            try:
                if len(old)+len(new)>250000:diff.append('Generated/large artifact change: '+name+'\n');continue
                diff.extend(difflib.unified_diff(old.decode('utf-8-sig').splitlines(True),new.decode('utf-8-sig').splitlines(True),fromfile='before/'+name,tofile='after/'+name))
            except UnicodeError:diff.append('Binary change: '+name+'\n')
    (BACKUP/'release.diff').write_text(''.join(diff),encoding='utf-8')
    print('Verified backup; changes:',len(changes),{s:sum(v['status']==s for v in changes.values()) for s in ['modified','added','deleted']})
if __name__=='__main__':main()
