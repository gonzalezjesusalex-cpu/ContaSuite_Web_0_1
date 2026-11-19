"""Lanzador de escritorio para desarrollo: un doble clic abre ContaSuite en su propia ventana.

Flujo: recompila el frontend sólo si cambiaron sus entradas -> inicia los componentes necesarios (PostgreSQL propio
cuando la instancia lo trae, API y trabajadores) -> abre una ventana de aplicación (Edge/Chrome en modo --app con
perfil propio) -> al cerrarla detiene, en orden, únicamente lo que ESTA apertura inició.

La instancia (base, documentos, usuarios, configuración, perfil de la ventana) vive aparte del código:
  * por omisión, una instancia sintética de pruebas en %LOCALAPPDATA%\\ContaSuite\\dev (SQLite declarado como prueba);
  * `--instance CARPETA` con una instalación local aislada (LOCAL_INSTALLATION.json): usa su PostgreSQL privado.
Nada se migra, siembra ni reinicia al abrir. No registra servicios, inicio automático ni reglas de firewall.
"""

import argparse
import ctypes
import hashlib
import json
import os
import queue
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / 'frontend'
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
INSTANCE_FORMAT = 'contasuite-dev-instance-v1'
# Never the old instance (8000), pilot (8062), local install (8072) or `npm run dev` (8090-8099).
PORT_RANGE = range(8100, 8150)
STOP_FILE = 'private/dev-stop.request'
RUN_FILE = 'private/dev-launcher-run.json'
LOCK_FILE = 'private/dev-launcher.lock'
STATUS_FILE = 'private/dev-host-status.json'
STAMP = '.launcher-build.json'
WINDOW_FILE = 'private/dev-window.json'
AGENT_PORT = 47865  # fixed port the web app uses to reach the local agent
SHORTCUT_NAME = 'ContaSuite.lnk'
BUILD_DIRS = ('src', 'public')
BUILD_FILES = (
    'index.html',
    'package.json',
    'package-lock.json',
    'vite.config.ts',
    'tsconfig.json',
    'tailwind.config.cjs',
    'postcss.config.cjs',
)
HOST_TIMEOUT = 120  # seconds until the API reports ready
GRACE = 40  # seconds of orderly shutdown before asking whether to keep waiting
JOB_NAMES = {
    'scan_folder': 'análisis de carpeta',
    'export_virtual': 'exportación de una copia',
    'sat_declaraciones': 'descarga de declaraciones del SAT',
}


class LauncherError(Exception):
    """A problem the user can understand; the message is shown as is (never contains secrets)."""


# ---------------------------------------------------------------------------------------------------- frontend


def frontend_digest(frontend=FRONTEND):
    """SHA-256 over the relevant build inputs (paths + contents): code, public assets, configuration, lockfile."""
    digest = hashlib.sha256()
    paths = [frontend / name for name in BUILD_FILES if (frontend / name).is_file()]
    for directory in BUILD_DIRS:
        paths.extend(p for p in (frontend / directory).rglob('*') if p.is_file())
    for path in sorted(paths, key=lambda p: p.relative_to(frontend).as_posix()):
        digest.update(path.relative_to(frontend).as_posix().encode() + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def build_is_current(frontend=FRONTEND, digest=None):
    stamp = frontend / 'dist' / STAMP
    try:
        recorded = json.loads(stamp.read_text(encoding='utf-8')).get('digest')
    except (OSError, ValueError):
        return False
    return (frontend / 'dist' / 'index.html').is_file() and recorded == (digest or frontend_digest(frontend))


def find_npm():
    for candidate in (shutil.which('npm.cmd'), shutil.which('npm')):
        if candidate:
            return candidate
    for base in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)')):
        if base and (Path(base) / 'nodejs/npm.cmd').is_file():
            return str(Path(base) / 'nodejs/npm.cmd')
    return None


def ensure_frontend(log_file, frontend=FRONTEND, run=subprocess.run, progress=lambda text: None):
    """Build only when inputs changed. A build counts as valid only when it finished and was swapped in whole."""
    digest = frontend_digest(frontend)  # taken before building: edits made during the build trigger a rebuild
    if build_is_current(frontend, digest):
        return False
    npm = find_npm()
    if not npm or not (frontend / 'node_modules').is_dir():
        raise LauncherError(
            'No se puede compilar la interfaz: faltan Node.js o las dependencias del frontend '
            '(ejecuta una vez CONSTRUIR_FRONTEND.bat). No se abrió ninguna versión anterior.'
        )
    progress('Compilando la interfaz…')
    staging, previous, dist = frontend / '.dist-staging', frontend / '.dist-previous', frontend / 'dist'
    shutil.rmtree(staging, ignore_errors=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open('wb') as log:
        result = run(
            [npm, 'run', 'build', '--', '--outDir', staging.name, '--emptyOutDir'],
            cwd=frontend,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=FLAGS,
            timeout=900,
        )
    if result.returncode or not (staging / 'index.html').is_file():
        shutil.rmtree(staging, ignore_errors=True)
        tail = log_file.read_text(encoding='utf-8', errors='replace').strip().splitlines()[-6:]
        raise LauncherError(
            'La compilación de la interfaz falló y no se abrió ninguna versión anterior.\n\n'
            + '\n'.join(tail)
            + '\n\nDetalle completo: '
            + str(log_file)
        )
    (staging / STAMP).write_text(json.dumps({'digest': digest, 'built_at': time.time()}), encoding='utf-8')
    shutil.rmtree(previous, ignore_errors=True)
    if dist.exists():
        dist.rename(previous)
    try:
        staging.rename(dist)
    except OSError:
        if previous.exists():
            previous.rename(dist)
        raise
    shutil.rmtree(previous, ignore_errors=True)
    return True


# ---------------------------------------------------------------------------------------------------- instance


def default_instance():
    return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ContaSuite' / 'dev'


def settings_file():
    return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ContaSuite' / 'dev-launcher.json'


def saved_instance(settings=None):
    try:
        value = json.loads((settings or settings_file()).read_text(encoding='utf-8')).get('instance')
    except (OSError, ValueError):
        return None
    return Path(value) if isinstance(value, str) and value else None


def save_instance(root, settings=None):
    settings = settings or settings_file()
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps({'instance': str(Path(root).resolve())}), encoding='utf-8')


def resolve_instance(argument=None, environment=None, settings=None):
    """Explicit --instance > CONTASUITE_INSTANCE > remembered default > synthetic test instance."""
    return Path(argument or environment or saved_instance(settings) or default_instance())


def port_is_free(port):
    with socket.socket() as sock:
        return sock.connect_ex(('127.0.0.1', port)) != 0


def choose_port(is_free=port_is_free):
    for port in PORT_RANGE:
        if is_free(port):
            return port
    raise LauncherError('No hay un puerto libre entre 8100 y 8149 para una instancia nueva.')


class Instance:
    """Where an instance lives. Layout shared by both kinds: private/ (DPAPI configuration), data/, logs/."""

    def __init__(self, root, kind, port, database=None):
        self.root, self.kind, self.port, self.database = Path(root), kind, port, database

    @property
    def url(self):
        return 'http://127.0.0.1:' + str(self.port)

    def path(self, relative):
        return self.root / relative

    @classmethod
    def open(cls, root):
        root = Path(root).resolve()
        if (root / 'LOCAL_INSTALLATION.json').is_file():
            from local_setup import marker

            values = marker(root)  # raises ValueError when it is not a verifiable installation
            return cls(root, 'postgres', values['api_port'], values['database'])
        try:
            values = json.loads((root / 'INSTANCE.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        if values.get('format') != INSTANCE_FORMAT or not isinstance(values.get('port'), int):
            raise LauncherError('INSTANCE.json no es de esta versión del lanzador; no se tocó la carpeta.')
        return cls(root, 'sqlite', values['port'])

    @classmethod
    def create(cls, root, python, notify=lambda text: None, is_free=port_is_free):
        """First open of a new synthetic instance: explicit schema creation, DPAPI configuration, marker last."""
        root = Path(root).resolve()
        if root.exists() and any(root.iterdir()):
            raise LauncherError(
                'La carpeta de la instancia existe pero no está completa (creación interrumpida): '
                + str(root)
                + '\nSe conserva sin tocar; renómbrala o elige otra con --instance.'
            )
        notify('Creando la instancia de pruebas (sólo la primera vez)…')
        from local_setup import write_secret

        for name in ('private', 'data', 'logs'):
            (root / name).mkdir(parents=True, exist_ok=True)
        port = choose_port(is_free)
        config = {
            'DATABASE_URL': 'sqlite:///' + (root / 'contasuite.db').as_posix(),
            'APP_TOKEN': secrets.token_urlsafe(32),
            'CS_TEST_SQLITE': '1',
            'CS_ALLOWED_HOSTS': '["127.0.0.1","localhost"]',
            'CS_STORAGE_ALLOWED_ROOTS': '[]',
            'CS_STORAGE_SMB_ALLOWED_ROOTS': '[]',
        }
        write_secret(root / 'private/service.json', config)
        result = subprocess.run(
            [
                str(python),
                '-B',
                str(ROOT / 'scripts/schema_admin.py'),
                '--data-dir',
                str(root / 'data'),
                '--new',
                '--apply',
            ],
            env=host_environment(config, root),
            capture_output=True,
            creationflags=FLAGS,
            timeout=300,
        )
        if result.returncode:
            raise LauncherError('No se pudo crear la base de la instancia nueva. Se conservó: ' + str(root))
        (root / 'INSTANCE.json').write_text(
            json.dumps({'format': INSTANCE_FORMAT, 'id': uuid4().hex, 'kind': 'sqlite-test', 'port': port}, indent=2),
            encoding='utf-8',
        )
        return cls(root, 'sqlite', port)


def host_environment(config, root):
    """Environment for children: the DPAPI configuration plus the usual explicit flags; never a dotenv fallback."""
    env = dict(os.environ)
    env.update(config)
    env.update(
        PYTHON_DOTENV_DISABLED='1',
        DATA_DIR=str(Path(root) / 'data'),
        SEED_DEMO='false',
        NO_PROXY='127.0.0.1,localhost',
        PYTHONPATH=os.pathsep.join([str(ROOT / 'backend'), str(ROOT / 'scripts')]),
    )
    # The shared agent token is off by default; execute() only needs a throwaway value to start.
    env.setdefault('AGENT_TOKEN', secrets.token_urlsafe(48))
    return env


def find_app_python(candidates=None, check=None, instance_root=None):
    """First interpreter that imports the backend. The repository .venv may belong to another PC: it is tried, not assumed."""
    if candidates is None:
        candidates = [
            os.environ.get('CONTA_PYTHON'),
            instance_root and Path(instance_root) / 'runtime/python.exe',  # private runtime of an installation
            ROOT / '.venv/Scripts/python.exe',
        ]
    probe = check or (
        lambda p: subprocess.run(
            [str(p), '-c', 'import fastapi, uvicorn, sqlalchemy, httpx'],
            capture_output=True,
            creationflags=FLAGS,
            timeout=60,
        ).returncode
        == 0
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            try:
                if probe(candidate):
                    return Path(candidate)
            except (OSError, subprocess.SubprocessError):
                pass
    raise LauncherError(
        'No hay un Python con las dependencias del backend. Crea un entorno con backend\\requirements.txt y '
        'apunta la variable CONTA_PYTHON a su python.exe (el .venv de esta carpeta puede ser de otra PC).'
    )


def find_browser():
    names = ('Microsoft/Edge/Application/msedge.exe', 'Google/Chrome/Application/chrome.exe')
    bases = [os.environ.get(k) for k in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA')]
    candidates = [os.environ.get('CS_BROWSER')] + [Path(b) / n for b in bases if b for n in names]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise LauncherError('Hace falta Microsoft Edge o Google Chrome para abrir la ventana (o define CS_BROWSER).')


# ---------------------------------------------------------------------------------------------------- processes


def process_identity(pid):
    """Creation time of a live process (None when gone): proves a recorded pid is still the process we started."""
    if os.name != 'nt':
        return None
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        created, exited, kernel_time, user_time = (ctypes.c_ulonglong() for _ in range(4))  # FILETIME = 64 bits
        if not kernel.GetProcessTimes(
            ctypes.c_void_p(handle), *[ctypes.byref(v) for v in (created, exited, kernel_time, user_time)]
        ):
            return None
        return created.value if exited.value == 0 else None
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


class Job:
    """Windows job object: its processes die with the launcher, and `active()` says if any is still alive."""

    def __init__(self):
        self.handle = None
        if os.name != 'nt':
            return
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [
                ('PerProcessUserTimeLimit', ctypes.c_longlong),
                ('PerJobUserTimeLimit', ctypes.c_longlong),
                ('LimitFlags', w.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', w.DWORD),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', w.DWORD),
                ('SchedulingClass', w.DWORD),
            ]

        class Counters(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ('r', 'w', 'o', 'rb', 'wb', 'ob')]

        class Extended(ctypes.Structure):
            _fields_ = [
                ('Basic', Basic),
                ('Io', Counters),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t),
                ('PeakJobMemoryUsed', ctypes.c_size_t),
            ]

        class Accounting(ctypes.Structure):
            _fields_ = [
                (n, ctypes.c_longlong)
                for n in ('TotalUserTime', 'TotalKernelTime', 'ThisPeriodUser', 'ThisPeriodKernel')
            ] + [
                (n, w.DWORD)
                for n in ('TotalPageFaultCount', 'TotalProcesses', 'ActiveProcesses', 'TotalTerminatedProcesses')
            ]

        self._accounting = Accounting
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.restype = ctypes.c_void_p
        self.handle = ctypes.c_void_p(self.kernel.CreateJobObjectW(None, None))
        info = Extended()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError('No se pudo preparar el grupo de procesos de la ventana.')

    def add(self, process):
        if self.handle is not None and not self.kernel.AssignProcessToJobObject(
            self.handle, ctypes.c_void_p(process._handle)
        ):
            raise OSError('No se pudo asociar la ventana a su grupo de procesos.')

    def active(self):
        if self.handle is None:
            return 0
        info = self._accounting()
        self.kernel.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None)
        return info.ActiveProcesses

    def terminate(self):
        if self.handle is not None:
            self.kernel.TerminateJobObject(self.handle, 1)

    def pids(self):
        """Process ids currently inside the job (JobObjectBasicProcessIdList)."""
        if self.handle is None:
            return []
        buffer = (ctypes.c_size_t * 258)()  # two DWORD counters share the first word; ids follow
        if not self.kernel.QueryInformationJobObject(self.handle, 3, buffer, ctypes.sizeof(buffer), None):
            return []
        listed = min(buffer[0] >> 32, 256)
        return sorted(buffer[1 + i] for i in range(listed))


class Owned:
    """A process this opening started, recorded with its creation time so a crash can be cleaned up safely."""

    def __init__(self, name, proc, created=None):
        self.name, self.proc, self.created = name, proc, created


def spawn(args, **kwargs):
    return subprocess.Popen([str(a) for a in args], stdin=subprocess.DEVNULL, **kwargs)


def resume_process(process):
    if os.name == 'nt':
        ctypes.windll.ntdll.NtResumeProcess(ctypes.c_void_p(process._handle))


def http_ok(url, timeout=1.5):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback must never go through a proxy
    try:
        with opener.open(url, timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def focus_windows(pids):
    """Bring the visible top-level windows of these processes to the front. Returns True when one was found."""
    if os.name != 'nt' or not pids:
        return False
    user32 = ctypes.windll.user32
    found = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(handle, _):
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(handle), ctypes.byref(owner))
        if (
            owner.value in pids
            and user32.IsWindowVisible(ctypes.c_void_p(handle))
            and user32.GetWindowTextLengthW(ctypes.c_void_p(handle))
        ):
            found.append(handle)
        return True

    user32.EnumWindows(callback_type(visit), None)
    for handle in found:
        if user32.IsIconic(ctypes.c_void_p(handle)):
            user32.ShowWindow(ctypes.c_void_p(handle), 9)  # SW_RESTORE
        user32.SetForegroundWindow(ctypes.c_void_p(handle))
    return bool(found)


def focus_existing(instance):
    try:
        pids = json.loads(instance.path(WINDOW_FILE).read_text(encoding='utf-8')).get('pids', [])
    except (OSError, ValueError):
        return False
    return focus_windows(set(pids))


def make_icon(png, ico):
    """ICO container around the existing ContaSuite PNG (PNG payloads are valid ICO entries)."""
    import struct

    data = Path(png).read_bytes()
    width, height = struct.unpack('>II', data[16:24])
    entry = struct.pack('<BBBBHHII', width % 256, height % 256, 0, 0, 1, 32, len(data), 22)
    Path(ico).write_bytes(struct.pack('<HHH', 0, 1, 1) + entry + data)
    return Path(ico)


def create_shortcut(instance_root, name=SHORTCUT_NAME, desktop=None):
    """Desktop shortcut: windowless pythonw, the existing ContaSuite icon, no arguments (default instance is remembered)."""
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    icon = make_icon(
        ROOT / 'frontend/public/icons/original/claro/128/CS_ContaSuite.png', Path(instance_root) / 'contasuite.ico'
    )
    env = dict(
        os.environ,
        CS_TARGET=str(pythonw),
        CS_ARGS='-B "' + str(Path(__file__).resolve()) + '"',
        CS_DIR=str(ROOT),
        CS_ICON=str(icon),
        CS_NAME=name,
        CS_DESKTOP=str(desktop or ''),
    )
    script = (
        "$d = if ($env:CS_DESKTOP) { $env:CS_DESKTOP } else { [Environment]::GetFolderPath('Desktop') }; "
        '$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d $env:CS_NAME)); '
        '$s.TargetPath = $env:CS_TARGET; $s.Arguments = $env:CS_ARGS; $s.WorkingDirectory = $env:CS_DIR; '
        "$s.IconLocation = $env:CS_ICON; $s.Description = 'ContaSuite (desarrollo)'; $s.Save(); $s.FullName"
    )
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
        env=env,
        capture_output=True,
        text=True,
        creationflags=FLAGS,
        timeout=60,
    )
    if result.returncode:
        raise LauncherError('No se pudo crear el acceso directo.')
    return result.stdout.strip()


def message_box(text, title='ContaSuite', style=0x40):
    """Native dialog (no console, no tkinter). Returns the button id (6 = Yes, 7 = No, 1 = OK)."""
    if os.name != 'nt':
        print(title + ': ' + text)
        return 1
    return ctypes.windll.user32.MessageBoxW(None, text, title, style | 0x10000)


def copy_to_clipboard(text):
    subprocess.run(['clip.exe'], input=text.encode('utf-16le'), creationflags=FLAGS, timeout=10)


# ---------------------------------------------------------------------------------------------------- launcher


class Launcher:
    """One opening: owns what it starts and stops exactly that. Platform pieces are attributes so tests can replace them."""

    def __init__(self, instance, python=None, browser=None, notify=lambda text: None):
        self.instance, self.python, self.browser = instance, python, browser
        self.notify = notify
        self.owned = []
        self.job = self.host_job = None
        self.token = uuid4().hex
        self.postgres_owned = False
        self.lock = None
        self.with_agent = False
        self.agent_job = None
        self.last_pids = None
        # Replaceable platform hooks (tests inject doubles; defaults are the real thing).
        self.spawn, self.identity, self.health, self.make_job = spawn, process_identity, http_ok, Job
        self.resume = resume_process
        self.ask_wait = lambda text: message_box(text, style=0x24) == 6
        self.error = lambda text: message_box(text, style=0x10)
        self.warn = lambda text: message_box(text, style=0x30)
        self.start_postgres = self.stop_postgres = self.postgres_running = None
        self.build_frontend = lambda: ensure_frontend(instance.path('logs/frontend-build.log'), progress=notify)
        self.free = port_is_free
        self.sleep = time.sleep
        self.host_timeout, self.grace = HOST_TIMEOUT, GRACE
        # Jobs of the local agent (what it is running now, and marking them failed on an interruption).
        self.agent_jobs, self.interrupt_jobs, self.job_poll = self.running_agent_jobs, self.interrupt_agent_jobs, 5

    def log(self, text):
        try:
            with self.instance.path('logs/launcher.log').open('a', encoding='utf-8') as stream:
                stream.write(time.strftime('%Y-%m-%d %H:%M:%S ') + text + '\n')
        except OSError:
            pass

    # -- bookkeeping ------------------------------------------------------------------------------------------
    def record(self):
        data = {
            'launcher_pid': os.getpid(),
            'postgres_owned': self.postgres_owned,
            'components': [{'name': o.name, 'pid': o.proc.pid, 'created': o.created} for o in self.owned],
        }
        path = self.instance.path(RUN_FILE)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data), encoding='utf-8')
        os.replace(temporary, path)

    def forget(self):
        for name in (RUN_FILE, STOP_FILE, WINDOW_FILE):
            self.instance.path(name).unlink(missing_ok=True)

    def adopt(self, name, proc):
        self.owned.append(Owned(name, proc, self.identity(proc.pid)))
        self.record()

    # -- single instance ----------------------------------------------------------------------------------------
    def acquire(self):
        if self.lock:
            return True
        import msvcrt

        handle = self.instance.path(LOCK_FILE).open('a+b')
        try:
            handle.seek(0)
            handle.write(b'0')
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            return False
        self.lock = handle
        return True

    def release(self):
        if self.lock:
            self.lock.close()
            self.lock = None

    # -- recovery of a previous crash: only processes whose pid AND creation time were recorded by us -----------------
    def recover(self, kill=None):
        self.instance.path(WINDOW_FILE).unlink(missing_ok=True)  # pids of a previous opening may have been reused
        path = self.instance.path(RUN_FILE)
        try:
            previous = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return
        kill = kill or (lambda pid: os.kill(pid, 15))
        for item in reversed(previous.get('components', [])):
            if item.get('created') and self.identity(item['pid']) == item['created']:
                kill(item['pid'])
        if previous.get('postgres_owned') and self.postgres_running and self.postgres_running(self.instance.root):
            self.stop_postgres(self.instance.root)
        path.unlink(missing_ok=True)

    # -- startup ----------------------------------------------------------------------------------------------
    def preflight(self):
        if self.instance.kind == 'postgres':
            from local_runtime import alive

            if alive(self.instance.root):
                raise LauncherError(
                    'Esta instalación ya está en marcha con ABRIR_CONTASUITE o el servicio; ciérrala allí antes de usar el lanzador.'
                )
        if not self.free(self.instance.port):
            raise LauncherError(
                'El puerto '
                + str(self.instance.port)
                + ' lo usa otro programa que no es esta instancia. ContaSuite no se conecta a servicios desconocidos: '
                'ciérralo y vuelve a abrir.'
            )

    def start_host(self):
        inst = self.instance
        for name in (STATUS_FILE, STOP_FILE):
            inst.path(name).unlink(missing_ok=True)
        if inst.kind == 'postgres':
            self.notify('Iniciando PostgreSQL de la instalación…')
            if self.postgres_running(inst.root):
                raise LauncherError(
                    'PostgreSQL de esta instalación ya estaba activo (no lo inició esta apertura), así que el lanzador no '
                    'puede garantizar su cierre. Deténlo con DETENER_CONTASUITE.cmd y vuelve a abrir.'
                )
            try:
                self.start_postgres(inst.root)
            finally:
                # It was verified stopped just above: whatever is running now was started by this opening, even if the
                # post-start identity check failed, so it must be closed with the rest.
                if self.postgres_running(inst.root):
                    self.postgres_owned = True
                    self.record()
        self.notify('Iniciando ContaSuite…')
        from secure_config import load

        env = host_environment(load(inst.path('private/service.json')), inst.root)
        env['CS_LAUNCH_TOKEN'] = self.token
        self.host_job = self.make_job()
        proc = self.spawn(
            [self.python, '-B', Path(__file__).resolve(), '--host', '--instance', inst.root],
            env=env,
            cwd=ROOT / 'backend',
            creationflags=FLAGS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.host_job.add(proc)  # a venv python.exe is only a shim: the job covers the real interpreter too
        self.adopt('api', proc)
        deadline = time.monotonic() + self.host_timeout
        while time.monotonic() < deadline:
            status = self.read_status()
            if proc.poll() is not None:
                raise LauncherError(
                    status.get('message')
                    or 'La aplicación se detuvo al iniciar. Revisa ' + str(inst.path('logs/service.log'))
                )
            if (
                status.get('state') == 'running'
                and status.get('token') == self.token
                and self.health(inst.url + '/api/health')
            ):
                if status.get('pid') != proc.pid:
                    self.adopt('api-interprete', SimpleNamespace(pid=status['pid']))
                return
            self.sleep(0.25)
        raise LauncherError('ContaSuite no estuvo lista a tiempo. Revisa ' + str(inst.path('logs/service.log')))

    def read_status(self):
        try:
            return json.loads(self.instance.path(STATUS_FILE).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def start_agent(self):
        """Local agent of this development instance: own configuration, no tray icon, stopped on exit."""
        inst = self.instance
        if not self.free(AGENT_PORT):
            self.log('puerto del agente ocupado por otro proceso: no se adopta')
            self.warn(
                'Ya hay un agente local en el puerto '
                + str(AGENT_PORT)
                + ' que no inició esta apertura. No se adopta ni se detendrá. Para vincularlo con esta instancia, '
                'agrega ' + inst.url + ' a sus orígenes permitidos, o ciérralo y reabre ContaSuite.'
            )
            return
        config = {
            'api_url': inst.url,
            'local_port': AGENT_PORT,
            'app_origins': [inst.url, 'http://localhost:' + str(inst.port)],
            'log_file': str(inst.path('logs/agente.log')),
            'tray': False,
        }
        path = inst.path('agent-dev.json')
        path.write_text(json.dumps(config, indent=2), encoding='utf-8')
        self.notify('Iniciando el agente local…')
        self.agent_job = self.make_job()
        proc = self.spawn(
            [self.python, '-B', ROOT / 'agent/agent.py', '--config', path],
            cwd=ROOT / 'agent',
            creationflags=FLAGS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.agent_job.add(proc)
        self.adopt('agente', proc)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and proc.poll() is None and self.free(AGENT_PORT):
            self.sleep(0.25)
        if proc.poll() is not None or self.free(AGENT_PORT):
            self.log('el agente no inició; revisa logs/agente.log')
            self.warn('El agente local no pudo iniciar; ContaSuite abrirá sin él. Detalle: ' + str(inst.path('logs/agente.log')))

    def publish_window(self):
        """Process ids of the window, so a second opening can bring it to the front."""
        pids = getattr(self.job, 'pids', lambda: [])()
        if pids and pids != self.last_pids:
            self.last_pids = pids
            self.instance.path(WINDOW_FILE).write_text(json.dumps({'pids': pids}), encoding='utf-8')

    def open_window(self):
        profile = self.instance.path('browser-profile')
        profile.mkdir(exist_ok=True)
        self.job = self.make_job()
        # Edge/Chrome may hand the window to another process and exit at once, so the main process proves nothing:
        # start it suspended inside our job object (every descendant joins it), then resume.
        proc = self.spawn(
            [
                self.browser,
                '--app=' + self.instance.url,
                '--user-data-dir=' + str(profile),
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-background-mode',
                '--window-size=1366,860',
                *os.environ.get('CS_BROWSER_EXTRA_ARGS', '').split(),  # e.g. a debugging port for acceptance runs
            ],
            creationflags=0x4,  # CREATE_SUSPENDED
        )
        self.job.add(proc)
        self.adopt('ventana', proc)
        self.resume(proc)

    def wait_window(self, appear_timeout=60):
        """Block until the last process of the window's job is gone (the window was closed)."""
        deadline = time.monotonic() + appear_timeout
        while self.job.active() == 0:
            if time.monotonic() > deadline:
                raise LauncherError('La ventana de la aplicación no se abrió. Comprueba Edge o Chrome (CS_BROWSER).')
            self.sleep(0.2)
        while self.job.active() > 0:
            self.publish_window()
            self.sleep(0.5)

    # -- jobs of the local agent: internal path, never an endpoint --------------------------------------------------
    def jobs_child(self, *args):
        """Run `--jobs` in a child with the instance's own protected configuration (it opens the instance's database)."""
        from secure_config import load

        env = host_environment(load(self.instance.path('private/service.json')), self.instance.root)
        result = subprocess.run(
            [str(self.python), '-B', str(Path(__file__).resolve()), *args, '--instance', str(self.instance.root)],
            env=env,
            cwd=ROOT / 'backend',
            capture_output=True,
            creationflags=FLAGS,
            timeout=60,
        )
        if result.returncode:
            raise LauncherError('No se pudo consultar los trabajos del agente (código ' + str(result.returncode) + ').')
        return json.loads(result.stdout.decode('utf-8'))

    def running_agent_jobs(self):
        """[{'id', 'kind', 'company_id'}] of the jobs that are `running` in this instance."""
        return self.jobs_child('--jobs', 'list')

    def interrupt_agent_jobs(self, ids):
        """Mark those jobs failed with «Interrumpido al cerrar ContaSuite»; returns the ids that were marked."""
        return self.jobs_child('--jobs', 'interrupt', *[arg for i in ids for arg in ('--job-id', i)])

    def wait_for_agent_jobs(self):
        """Closing must not cut the agent's work silently: ask whether to wait for it (same question as the server's).

        Returns the ids of the jobs the person chose to interrupt ([] when there were none, or they finished).
        """
        try:
            jobs = self.agent_jobs()
        except Exception as exc:  # noqa: BLE001 - not knowing is not a reason to block the closing
            self.log('no se pudieron consultar los trabajos del agente: ' + type(exc).__name__)
            return []
        waited = None
        while jobs:
            if waited is None or waited >= self.grace:
                names = ', '.join(sorted({JOB_NAMES.get(j['kind'], j['kind']) for j in jobs}))
                if not self.ask_wait(
                    'Tu agente local sigue trabajando (' + names + ').\n\n¿Esperar a que termine?\n'
                    'Sí = seguir esperando · No = interrumpir ahora (el trabajo quedará como fallido).'
                ):
                    self.log('interrupción del agente confirmada por el usuario')
                    return [j['id'] for j in jobs]
                waited = 0
            self.sleep(self.job_poll)
            waited += self.job_poll
            try:
                jobs = self.agent_jobs()
            except Exception as exc:  # noqa: BLE001
                self.log('no se pudieron consultar los trabajos del agente: ' + type(exc).__name__)
                return []
        return []

    # -- shutdown ----------------------------------------------------------------------------------------------
    def stop_all(self):
        """Reverse order of startup: window, API/workers, then PostgreSQL last. Only what this opening owns."""
        window = next((o for o in self.owned if o.name == 'ventana'), None)
        if window:
            if self.job:
                self.sleep(0)  # let the main browser process finish its own exit first
                self.job.terminate()
            elif window.proc.poll() is None:
                window.proc.kill()
        agent = next((o for o in self.owned if o.name == 'agente'), None)
        interrupted = self.wait_for_agent_jobs() if agent else []
        if agent:
            if self.agent_job:
                self.agent_job.terminate()
            if agent.proc.poll() is None:
                agent.proc.kill()
        if interrupted:  # the server is still up: its jobs would stay `running` until they expire
            try:
                self.interrupt_jobs(interrupted)
            except Exception as exc:  # noqa: BLE001 - reported, and the closing goes on
                self.log('no se pudieron marcar los trabajos interrumpidos: ' + type(exc).__name__)
        host = next((o for o in self.owned if o.name == 'api'), None)
        problems = []
        if host:
            self.instance.path(STOP_FILE).write_text('stop', encoding='ascii')
            waited = 0
            while host.proc.poll() is None:
                if waited >= self.grace:
                    if self.ask_wait(
                        'ContaSuite sigue terminando trabajos en curso.\n\n¿Esperar a que terminen?\n'
                        'Sí = seguir esperando · No = interrumpir ahora (puede dejar un trabajo a medias).'
                    ):
                        waited = 0
                    else:
                        self.log('interrupción confirmada por el usuario')
                        self.host_job.terminate()
                        host.proc.kill()
                        host.proc.wait(timeout=15)
                        break
                self.sleep(0.5)
                waited += 0.5
        if self.postgres_owned:
            try:
                self.stop_postgres(self.instance.root)
            except Exception as exc:  # noqa: BLE001 - shutdown must report, never hide, a database that did not stop
                problems.append('PostgreSQL no se detuvo: ' + type(exc).__name__)
            else:
                self.postgres_owned = False
        self.owned.clear()
        if problems:
            self.record()
            raise LauncherError('; '.join(problems) + '. Los datos se conservaron; revisa logs/postgres.log.')
        self.forget()

    # -- entry points --------------------------------------------------------------------------------------------
    def run(self):
        """Complete opening. Returns True when the window was shown and closed normally."""
        if not self.acquire():
            self.error('ContaSuite ya está abierta (o cerrándose) para esta instancia.')
            return False
        try:
            self.recover()
            self.build_frontend()
            self.preflight()
            self.start_host()
            if self.with_agent:
                self.start_agent()
            self.open_window()
            self.notify('')
            self.wait_window()
            return True
        except LauncherError as exc:
            self.log('error: ' + str(exc).splitlines()[0])
            self.error(str(exc))
            return False
        except Exception as exc:  # noqa: BLE001 - last resort: tell the user, then the finally block still closes what we own
            self.log('error inesperado: ' + repr(exc))
            self.error('No se completó la apertura (' + type(exc).__name__ + '). Los datos y registros se conservaron.')
            return False
        finally:
            self.notify('Cerrando ContaSuite…')
            try:
                self.stop_all()
            except LauncherError as exc:
                self.error(str(exc))
            self.release()


# ---------------------------------------------------------------------------------------------------- host child


def host_main(instance_root):
    """Child process: API + workers through the existing windows_service.execute; stops on the stop-request file."""
    inst = Instance.open(instance_root)
    status_file = inst.path(STATUS_FILE)

    def report(state, error, message=None):
        names = {1: 'stopped', 2: 'starting', 3: 'stopping', 4: 'running'}
        status_file.write_text(
            json.dumps(
                {
                    'state': names.get(state, state),
                    'error': error,
                    'pid': os.getpid(),
                    'token': os.environ.get('CS_LAUNCH_TOKEN'),
                    'message': message,
                }
            ),
            encoding='utf-8',
        )

    from secure_config import load
    from windows_service import Lifecycle, execute

    os.environ.update(host_environment(load(inst.path('private/service.json')), inst.root))
    sys.path[:0] = [str(ROOT / 'backend')]
    try:  # never migrates: an incompatible schema is reported and the database is kept as is
        from app.database import engine
        from app.schema_compatibility import assert_schema

        assert_schema(engine)
    except BaseException as exc:  # noqa: BLE001 - reported to the launcher, which shows it and keeps everything
        report(
            1,
            1,
            'La base de esta instancia no es compatible con este código ('
            + type(exc).__name__
            + '); no se modificó nada.',
        )
        return 3
    lifecycle = Lifecycle(report)
    stop = inst.path(STOP_FILE)

    def watch():
        while not lifecycle.stop_event.wait(0.5):
            if stop.exists():
                lifecycle.stop()
                return

    threading.Thread(target=watch, daemon=True).start()
    return execute(lifecycle, inst.root / 'data', inst.port, inst.root / 'logs')


def jobs_main(instance_root, action, ids):
    """Child process: list the running jobs, or mark `ids` failed. Prints JSON; opens the instance's own database."""
    inst = Instance.open(instance_root)
    from secure_config import load

    os.environ.update(host_environment(load(inst.path('private/service.json')), inst.root))
    sys.path[:0] = [str(ROOT / 'backend')]
    from app.agent_jobs import interrupt_running_jobs, running_jobs
    from app.database import SessionLocal

    with SessionLocal() as db:
        out = running_jobs(db) if action == 'list' else interrupt_running_jobs(db, ids)
    sys.stdout.write(json.dumps(out))
    return 0


# ---------------------------------------------------------------------------------------------------- UI shell


def run_with_splash(launcher):
    """Small progress window while preparing/closing; the real work runs in a thread (mirrors local_install.py)."""
    messages = queue.Queue()
    launcher.notify = messages.put
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        return launcher.run()
    window = tk.Tk()
    window.title('ContaSuite')
    window.geometry('360x110')
    window.resizable(False, False)
    text = tk.StringVar(value='Preparando ContaSuite…')
    ttk.Label(window, textvariable=text, padding=16).pack()
    bar = ttk.Progressbar(window, mode='indeterminate')
    bar.pack(fill='x', padx=16)
    bar.start(12)
    window.protocol('WM_DELETE_WINDOW', lambda: None)  # closing is done by closing the application window
    outcome = []

    def work():
        try:
            outcome.append(launcher.run())
        finally:
            messages.put(None)

    def poll():
        while True:
            try:
                item = messages.get_nowait()
            except queue.Empty:
                break
            if item is None:
                window.destroy()
                return
            if item:
                text.set(item)
                window.deiconify()
            else:
                window.withdraw()  # the application window is up: hide the splash until closing
        window.after(100, poll)

    threading.Thread(target=work, daemon=True).start()
    poll()
    window.mainloop()
    return bool(outcome and outcome[0])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--instance', type=Path, help='Otra instancia; por omisión la recordada con --save-default')
    parser.add_argument('--host', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--jobs', choices=['list', 'interrupt'], help=argparse.SUPPRESS)
    parser.add_argument('--job-id', action='append', default=[], help=argparse.SUPPRESS)
    parser.add_argument('--save-default', action='store_true', help='Recuerda esta instancia como la predeterminada')
    parser.add_argument('--create-shortcut', action='store_true', help='Crea el acceso directo en el Escritorio')
    parser.add_argument(
        '--copy-key', action='store_true', help='Copia al portapapeles la clave del primer administrador'
    )
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    root = resolve_instance(args.instance, os.environ.get('CONTASUITE_INSTANCE'))
    if args.host:
        return host_main(root)
    if args.jobs:
        return jobs_main(root, args.jobs, args.job_id)
    try:
        python = find_app_python(instance_root=root)
        # The launcher itself imports psycopg (PostgreSQL identity check): run it with the application's interpreter.
        if (
            not os.environ.get('CS_LAUNCHER_REEXEC')
            and Path(sys.executable).resolve().parent != Path(python).resolve().parent
        ):
            gui = Path(python).with_name('pythonw.exe')
            subprocess.Popen(
                [str(gui if gui.is_file() else python), '-B', str(Path(__file__).resolve()), *sys.argv[1:]],
                env=dict(os.environ, CS_LAUNCHER_REEXEC='1'),
                creationflags=FLAGS,
            )
            return 0
        instance = Instance.open(root) if root.exists() else None
        if args.copy_key:
            from secure_config import load

            if instance is None:
                raise LauncherError('La instancia aún no existe: ábrela una vez.')
            copy_to_clipboard(load(instance.path('private/service.json'))['APP_TOKEN'])
            message_box('La clave de instalación se copió al portapapeles.')
            return 0
        if instance is None:
            instance = Instance.create(root, python)
            from secure_config import load

            copy_to_clipboard(load(instance.path('private/service.json'))['APP_TOKEN'])
            message_box(
                'Instancia nueva de pruebas creada en:\n'
                + str(instance.root)
                + '\n\nLa clave de instalación (para crear el primer administrador) se copió al portapapeles; '
                'pégala en la pantalla inicial. Podrás volver a copiarla con --copy-key.'
            )
        if args.save_default or args.create_shortcut:
            if instance is None:
                raise LauncherError('La instancia indicada aún no existe; ábrela una vez antes de recordarla.')
            if args.save_default:
                save_instance(instance.root)
            if args.create_shortcut:
                message_box('Acceso directo creado:\n' + create_shortcut(instance.root))
            return 0
        launcher = Launcher(instance, python, find_browser())
        launcher.with_agent = True
        if instance.kind == 'postgres':
            from local_setup import start_postgres, stop_postgres

            launcher.start_postgres, launcher.stop_postgres = start_postgres, stop_postgres
            launcher.postgres_running = postgres_is_running
    except (LauncherError, ValueError, OSError) as exc:
        message_box(
            str(exc) if isinstance(exc, LauncherError) else 'No se pudo preparar la apertura: ' + str(exc), style=0x10
        )
        return 1
    if not launcher.acquire():  # already open: bring its window to the front, start nothing
        if not focus_existing(instance):
            message_box('ContaSuite ya está abierta (o iniciándose). No se creó otra apertura.')
        return 0
    return 0 if run_with_splash(launcher) else 1


def postgres_is_running(root):
    return (
        subprocess.run(
            [str(root / 'postgresql/bin/pg_ctl.exe'), '-D', str(root / 'database'), 'status'],
            capture_output=True,
            creationflags=FLAGS,
        ).returncode
        == 0
    )


if __name__ == '__main__':
    raise SystemExit(main())
