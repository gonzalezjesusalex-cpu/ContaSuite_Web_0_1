"""Versioned installation with bundled runtime; never overwrites an existing installation/data."""
import argparse,json,hashlib,shutil,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
def verify(root):
    manifest=json.loads((root/'PACKAGE_SHA256.json').read_text(encoding='utf-8'))
    for name,digest in manifest.items():
        path=(root/name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise RuntimeError('Package verification failed: '+name)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['Install','Update','Uninstall'],required=True)
    parser.add_argument('--destination',type=Path,required=True);parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--backup',type=Path);parser.add_argument('--writers-stopped',action='store_true');args=parser.parse_args()
    source=Path(__file__).resolve().parents[2];dest=args.destination.resolve();data=args.data_dir.resolve()
    if not args.destination.is_absolute() or not args.data_dir.is_absolute():parser.error('Absolute installation/data directories required')
    if dest==source or dest.is_relative_to(source) or source.is_relative_to(dest) or data.is_relative_to(dest) or dest.is_relative_to(data):parser.error('Use separate installation, package and data directories')
    if args.mode=='Uninstall':
        if not args.writers_stopped or not (dest/'INSTALLATION.json').is_file():parser.error('Stop this installation and supply its installation marker')
        verify(dest)
        retired=dest.with_name(dest.name+'.retired-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S'))
        if retired.exists():parser.error('Retired destination already exists')
        dest.rename(retired)
        print('Installation retired reversibly; data/database/configuration preserved:',retired);return
    if args.mode=='Update' and (not args.writers_stopped or not args.backup or not args.backup.is_file()):parser.error('Update requires stopped writers and verified restored backup')
    if dest.exists():parser.error('Destination must be a new version directory; no overwrite')
    verify(source);shutil.copytree(source,dest)
    command=[str(dest/'runtime/python.exe'),'-B',str(dest/'app/scripts/schema_admin.py'),'--data-dir',str(data),'--apply']
    if args.mode=='Install':command+=['--new']
    else:command+=['--backup',str(args.backup)]
    result=subprocess.run(command,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('Schema update failed; retained installation for diagnosis, do not start it')
    (dest/'INSTALLATION.json').write_text(json.dumps({'release':'CS-RELEASE-CLOSURE-001','mode':args.mode,'data_external':True}),encoding='utf-8')
    print('Installation prepared; service/network registration remains explicit:',dest)
if __name__=='__main__':main()
