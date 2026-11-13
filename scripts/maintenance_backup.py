"""Scheduled maintenance backup with exclusive execution and persistent status.
Configuration is external and ACL protected. Runs under the backup service identity.
"""
import argparse,json,os,subprocess,sys,hashlib,shutil
from datetime import datetime,timezone
from pathlib import Path
from restore_postgres import verify

def run(config):
    values=json.loads(config.read_text(encoding='utf-8-sig'))
    required={'pg_bin','database','destination','data_dir','service','retention'}
    if set(values)!=required:raise ValueError('Invalid maintenance configuration')
    import re
    if not re.fullmatch(r'ContaSuite[A-Za-z0-9_]{0,40}',values['service']):raise ValueError('Dedicated ContaSuite service required')
    destination=Path(values['destination']);data=Path(values['data_dir']);pg=Path(values['pg_bin'])
    if not all(p.is_absolute() for p in (destination,data,pg)):raise ValueError('Absolute paths required')
    if not str(destination).startswith('\\\\'):raise ValueError('Scheduled backups require an external UNC destination')
    if not isinstance(values['retention'],int) or values['retention']<2:raise ValueError('Retain at least two verified backups')
    status=config.with_suffix('.status.json');lock=config.with_suffix('.lock')
    # Lock released by OS on crash; a stale file cannot disable future backups.
    import msvcrt
    with lock.open('a+b') as handle:
        handle.seek(0);handle.write(b'0');handle.flush();handle.seek(0)
        msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        stopped=False
        def command(args):
            result=subprocess.run(args,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode:raise RuntimeError('Maintenance operation failed: '+Path(args[0]).name)
            return result
        try:
            # Query through PowerShell's object API avoids parsing localized sc output.
            service=values['service']
            command(['powershell.exe','-NoProfile','-NonInteractive','-Command',f"$s=Get-Service -Name '{service}' -ErrorAction Stop; if($s.Status -ne 'Running'){{exit 2}}"])
            stopped=True
            command(['powershell.exe','-NoProfile','-NonInteractive','-Command',f"$ErrorActionPreference='Stop'; Stop-Service -Name '{service}'; (Get-Service -Name '{service}').WaitForStatus('Stopped',[TimeSpan]::FromSeconds(90))"])
            command([sys.executable,'-B',str(Path(__file__).with_name('backup_postgres.py')),'--pg-bin',str(pg),'--database',values['database'],'--destination',str(destination),'--data-dir',str(data),'--writers-stopped'])
            latest=max(destination.glob('contasuite-*'),key=lambda p:p.name)
            verify(latest)
            # Private configuration is protected by its ACL and external backup ACL;
            # credentials remain in the system account environment/PGPASSFILE, not this file.
            backups=sorted((p for p in destination.glob('contasuite-*') if p.is_dir()),reverse=True)
            for old in backups[values['retention']:]:
                verify(old)
                if old.resolve().parent!=destination.resolve():raise ValueError('Unsafe retention path')
                shutil.rmtree(old)
            result={'ok':True,'backup':latest.name,'at':datetime.now(timezone.utc).isoformat()}
            status.write_text(json.dumps(result),encoding='utf-8')
        except Exception as exc:
            status.write_text(json.dumps({'ok':False,'error_type':type(exc).__name__,'at':datetime.now(timezone.utc).isoformat()}),encoding='utf-8')
            raise
        finally:
            if stopped:command(['sc.exe','start',values['service']])

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args();run(args.config)
