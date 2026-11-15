"""Start the local agent with the Windows sign-in of the installing user (Bloque 4).

The installer writes `agent-session.json` (no token: the agent pairs at each ContaSuite sign-in) and a shortcut
in that user's Startup folder that runs the private runtime's pythonw.exe in the background. Nothing runs as a
service and no password or token is stored. `remove()` deletes the shortcut.
"""

import json
import os
import subprocess
from pathlib import Path

LOCAL_PORT = 47865
SHORTCUT = 'ContaSuite - Agente local.lnk'
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def startup_folder():
    return Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/Startup'


def write_config(root, api_port):
    log_dir = Path(os.environ.get('LOCALAPPDATA', root)) / 'ContaSuite'
    log_dir.mkdir(parents=True, exist_ok=True)
    origins = ['http://127.0.0.1:' + str(api_port), 'http://localhost:' + str(api_port)]
    config = {
        'api_url': origins[0],
        'local_port': LOCAL_PORT,
        'app_origins': origins,
        'log_file': str(log_dir / 'agente.log'),
    }
    path = Path(root) / 'agent-session.json'
    path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    return path


def register(root, api_port):
    """Config plus Startup shortcut for the current Windows user. Returns the shortcut path."""
    root = Path(root).resolve()
    config = write_config(root, api_port)
    link = startup_folder() / SHORTCUT
    # Paths travel as environment variables, never interpolated into the PowerShell command.
    env = dict(
        os.environ,
        CS_LNK=str(link),
        CS_TARGET=str(root / 'runtime/pythonw.exe'),
        CS_ARGS='-B "' + str(root / 'app/agent/agent.py') + '" --config "' + str(config) + '"',
        CS_DIR=str(root),
    )
    script = (
        '$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:CS_LNK); '
        '$s.TargetPath = $env:CS_TARGET; $s.Arguments = $env:CS_ARGS; $s.WorkingDirectory = $env:CS_DIR; '
        "$s.Description = 'Agente local de ContaSuite (sólo lectura)'; $s.Save()"
    )
    subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
        env=env,
        check=True,
        capture_output=True,
        creationflags=FLAGS,
        timeout=60,
    )
    return link


def start_now(root):
    """Launch the agent once right after installing, so it does not wait for the next Windows sign-in."""
    root = Path(root).resolve()
    subprocess.Popen(
        [
            str(root / 'runtime/pythonw.exe'),
            '-B',
            str(root / 'app/agent/agent.py'),
            '--config',
            str(root / 'agent-session.json'),
        ],
        cwd=str(root),
        creationflags=FLAGS,
        close_fds=True,
    )


def remove():
    (startup_folder() / SHORTCUT).unlink(missing_ok=True)
