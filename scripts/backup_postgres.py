"""Explicit maintenance backup. Never starts/stops services or deletes older backups."""
import argparse,os,json,hashlib,shutil,subprocess
from pathlib import Path
from datetime import datetime,timezone
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pg-bin',type=Path,required=True);parser.add_argument('--database',required=True)
    parser.add_argument('--destination',type=Path,required=True);parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--writers-stopped',action='store_true');args=parser.parse_args()
    if not args.writers_stopped:parser.error('Stop writers before a joint database/files backup')
    if not os.environ.get('PGHOST') or not os.environ.get('PGUSER'):parser.error('Explicit PGHOST/PGUSER required; no dotenv')
    if not args.destination.is_absolute() or not args.data_dir.is_absolute():parser.error('Absolute directories required')
    if args.destination.resolve().is_relative_to(args.data_dir.resolve()):parser.error('Backup destination must be outside data')
    output=args.destination/('contasuite-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'));output.mkdir(parents=True,exist_ok=False)
    try:
        subprocess.run([str(args.pg_bin/'pg_dump.exe'),'-Fc','--file',str(output/'database.dump'),'--dbname',args.database],check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.CalledProcessError:raise RuntimeError('pg_dump failed; partial backup retained for diagnosis') from None
    shutil.copytree(args.data_dir,output/'data')
    hashes={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file()}
    (output/'sha256.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print('Backup retained:',output,'Restore to another database and verify before approving it.')
if __name__=='__main__':main()
