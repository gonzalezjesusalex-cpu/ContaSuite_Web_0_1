"""Assemble a private Python 3.12 runtime from the tested local installation and RECORD files.
No network, configuration, registry, user site or credential files are included.
"""
import os,sys,zipfile,shutil,json,hashlib
from pathlib import Path
from importlib.metadata import distributions
def assemble(destination):
    assert sys.version_info[:2]==(3,12) and os.name=='nt'
    assert not destination.exists(),'Never overwrite a runtime'
    destination.mkdir(parents=True);base=Path(sys.base_prefix)
    for name in ['python.exe','pythonw.exe','python3.dll','python312.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt']:
        shutil.copy2(base/name,destination/name)
    shutil.copytree(base/'DLLs',destination/'DLLs',ignore=shutil.ignore_patterns('__pycache__','*.pdb','*.lib'))
    with zipfile.ZipFile(destination/'python312.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for parent,dirs,names in os.walk(base/'Lib'):
            dirs[:]=[d for d in dirs if d not in ('site-packages','__pycache__','test','tests','idlelib','tkinter','turtledemo','ensurepip')]
            for name in sorted(names):
                p=Path(parent)/name
                if p.suffix=='.py':archive.write(p,p.relative_to(base/'Lib').as_posix())
    packages=destination/'Lib/site-packages';packages.mkdir(parents=True)
    site=Path(sys.prefix)/'Lib/site-packages';copied=set();versions={}
    for distribution in distributions(path=[str(site)]):
        versions[distribution.metadata['Name']]=distribution.version
        for item in distribution.files or []:
            source=Path(distribution.locate_file(item)).resolve()
            if not source.is_relative_to(site.resolve()) or not source.is_file() or source.suffix in ('.pyc','.pth') or source.name=='direct_url.json':continue
            relative=source.relative_to(site.resolve())
            if '__pycache__' in relative.parts:continue
            target=packages/relative
            if relative.as_posix() not in copied:target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);copied.add(relative.as_posix())
    (destination/'python312._pth').write_text('python312.zip\n.\nDLLs\nLib/site-packages\n../app/backend\n../app/scripts\nimport site\n',encoding='utf-8')
    (destination/'RUNTIME_PROVENANCE.json').write_text(json.dumps({'python':sys.version.split()[0],'architecture':'win-amd64','source':'tested local CPython installation; isolated ._pth','distributions':versions},sort_keys=True,indent=2),encoding='utf-8')
    print('Private runtime files:',sum(1 for p in destination.rglob('*') if p.is_file()),'distributions:',len(versions))
if __name__=='__main__':assemble(Path(sys.argv[1]).resolve())
