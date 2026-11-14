"""Offline guided local installer from current source, clean runtimes and PostgreSQL binaries."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--postgresql', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'ENTREGAS/ContaSuite_Instalador_Pruebas_RC1.zip')
    args = parser.parse_args()
    if not (args.postgresql / 'bin/initdb.exe').is_file():
        parser.error('Clean PostgreSQL binaries required')
    for forbidden in ('PG_VERSION', 'postmaster.pid', 'postgresql.conf'):
        if (args.postgresql / forbidden).exists():
            parser.error('Never package a database cluster')
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / '.qa').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='local-installer-build-', dir=ROOT / '.qa') as temp:
        core = Path(temp) / 'core.zip'
        subprocess.run(
            [
                sys.executable,
                str(ROOT / 'scripts/package_release.py'),
                '--runtime',
                str(args.runtime),
                '--output',
                str(core),
            ],
            check=True,
        )
        extra = {}
        for name in (
            'local_setup',
            'local_runtime',
            'local_install',
            'apply_excel_fix',
            'managed_agent',
            'apply_agent',
            'queue_authorized_source',
        ):
            extra['app/scripts/' + name + '.py'] = ROOT / 'scripts' / (name + '.py')
        extra['app/agent/agent.py'] = ROOT / 'agent/agent.py'
        for name in (
            'INSTALAR_CONTASUITE',
            'ABRIR_CONTASUITE',
            'DETENER_CONTASUITE',
            'CONFIGURAR_CARPETAS',
            'ACTUALIZAR_EXCEL',
            'ACTUALIZAR_AGENTE',
        ):
            extra[name + '.cmd'] = ROOT / 'deploy/windows' / (name + '.cmd')
        extra['LEEME_INSTALADOR.txt'] = ROOT / 'docs/LOCAL_INSTALLER.txt'
        extra['LEEME_EXCEL.txt'] = ROOT / 'docs/EXCEL_FIX.txt'
        base = Path(sys.base_prefix)
        for folder, dest in [(base / 'Lib/tkinter', 'runtime/Lib/tkinter'), (base / 'tcl', 'runtime/tcl')]:
            for path in folder.rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                    extra[dest + '/' + path.relative_to(folder).as_posix()] = path
        for folder in ('bin', 'lib', 'share'):
            for path in (args.postgresql / folder).rglob('*'):
                if path.is_file():
                    extra['postgresql/' + path.relative_to(args.postgresql).as_posix()] = path
        for path in args.postgresql.glob('*license*.txt'):
            extra['postgresql/' + path.name] = path
        for path in args.postgresql.glob('*licenses*.txt'):
            extra['postgresql/' + path.name] = path
        override = {
            'runtime/python312._pth': b'python312.zip\n.\nDLLs\nLib\nLib/site-packages\n../app/backend\n../app/scripts\nimport site\n'
        }

        def build():
            manifest = {}
            with (
                zipfile.ZipFile(core) as source,
                zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive,
            ):

                def write(name, data):
                    info = zipfile.ZipInfo(name, (2026, 11, 12, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, data)
                    manifest[name] = hashlib.sha256(data).hexdigest()

                for name in sorted(source.namelist()):
                    if (
                        name not in {'PACKAGE_SHA256.json', 'INSTALL.cmd', 'START.cmd', 'ADMIN.cmd'}
                        and name not in extra
                        and name not in override
                    ):
                        write(name, source.read(name))
                for name, path in sorted(extra.items()):
                    write(name, path.read_bytes())
                for name, data in sorted(override.items()):
                    write(name, data)
                data = json.dumps(manifest, sort_keys=True, indent=2).encode()
                info = zipfile.ZipInfo('PACKAGE_SHA256.json', (2026, 11, 12, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
            return hashlib.sha256(output.read_bytes()).hexdigest(), len(manifest)

        digest, count = build()
        assert (digest, count) == build()
        with zipfile.ZipFile(output) as archive:
            assert archive.testzip() is None
        output.with_suffix('.sha256').write_text(digest + '  ' + output.name + '\n', encoding='ascii')
        print(json.dumps({'file': str(output), 'files': count, 'bytes': output.stat().st_size, 'sha256': digest}))


if __name__ == '__main__':
    main()
