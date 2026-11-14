"""Background supervisor for the isolated per-user installation; no SCM/network changes."""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from local_setup import marker, start_postgres, stop_postgres, FLAGS
from secure_config import load


def status(root):
    try:
        return json.loads((root / 'private/runtime-status.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'state': 'stopped'}


def alive(root):
    import msvcrt

    path = root / 'private/launcher.lock'
    if not path.exists():
        return False
    with path.open('r+b') as handle:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return True
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return False


def serve(root):
    import msvcrt

    values = marker(root)
    with (root / 'private/launcher.lock').open('a+b') as handle:
        handle.seek(0)
        handle.write(b'0')
        handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        stop = root / 'private/stop.request'
        stop.unlink(missing_ok=True)
        state_file = root / 'private/runtime-status.json'

        def report(state, error):
            state_file.write_text(
                json.dumps(
                    {
                        'state': {1: 'stopped', 2: 'starting', 3: 'stopping', 4: 'running'}[state],
                        'error': error,
                        'pid': os.getpid(),
                    }
                ),
                encoding='utf-8',
            )

        started = False
        from windows_service import Lifecycle, execute

        lifecycle = Lifecycle(report)
        try:
            report(2, 0)
            start_postgres(root)
            started = True
            config = load(root / 'private/service.json')
            os.environ.update(config)

            def watch():
                while not lifecycle.stop_event.wait(0.5):
                    if stop.exists():
                        lifecycle.stop()
                        return

            threading.Thread(target=watch, daemon=True).start()
            from managed_agent import run_agent

            result = execute(
                lifecycle,
                root / 'data',
                values['api_port'],
                root / 'logs',
                extra_workers=[('windows-agent', lambda event: run_agent(root, event))],
            )
            return result
        except BaseException:  # noqa: BLE001 - supervisor: reports failure in the status file and stops
            report(1, 1)
            return 1
        finally:
            lifecycle.stop_event.set()
            if started or (root / 'database/postmaster.pid').is_file():
                try:
                    stop_postgres(root)
                except Exception:  # noqa: BLE001 - supervisor: reports failure in the status file and stops
                    report(1, 1)


def start(root):
    values = marker(root)
    if not alive(root):
        # Refuse an unrelated listener before starting anything.
        from local_setup import free_port

        free_port(values['api_port'])
        subprocess.Popen(
            [
                str(root / 'runtime/pythonw.exe'),
                '-B',
                str(root / 'app/scripts/local_runtime.py'),
                '--root',
                str(root),
                '--serve',
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=FLAGS,
            cwd=root,
        )
    import httpx

    for _ in range(180):
        if status(root).get('state') == 'running':
            try:
                if (
                    httpx.get('http://127.0.0.1:' + str(values['api_port']) + '/api/health', timeout=1).status_code
                    == 200
                ):
                    return values
            except httpx.HTTPError:
                pass
        time.sleep(0.5)
    raise RuntimeError('No se pudo iniciar; consulta logs/service.log y logs/postgres.log de esta instalación.')


def stop(root):
    marker(root)
    if not alive(root):
        return
    (root / 'private/stop.request').write_text('stop', encoding='ascii')
    for _ in range(180):
        if not alive(root):
            return
        time.sleep(0.5)
    raise RuntimeError('La parada aún no terminó. Consulta los registros antes de volver a iniciar.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--stop', action='store_true')
    args = parser.parse_args()
    if args.serve:
        raise SystemExit(serve(args.root.resolve()))
    elif args.stop:
        stop(args.root.resolve())
    else:
        start(args.root.resolve())
