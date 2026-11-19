"""Pruebas enfocadas del lanzador de desarrollo: dobles de procesos, sin PostgreSQL ni compilaciones reales.

Ejecutar: python -m pytest scripts/test_dev_launcher.py -q   (sólo biblioteca estándar y pytest)
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dev_launcher as dl  # noqa: E402


# ------------------------------------------------------------------------------------------------ frontend


def make_frontend(root):
    (root / 'src').mkdir(parents=True)
    (root / 'public').mkdir()
    (root / 'node_modules').mkdir()
    (root / 'src/main.tsx').write_text('one', encoding='utf-8')
    (root / 'public/logo.svg').write_text('logo', encoding='utf-8')
    for name in ('package.json', 'package-lock.json', 'index.html', 'vite.config.ts'):
        (root / name).write_text(name, encoding='utf-8')
    return root


class FakeBuild:
    """Replaces `npm run build`: writes into the staging folder named in the arguments."""

    def __init__(self, code=0, write_index=True):
        self.calls, self.code, self.write_index = 0, code, write_index

    def __call__(self, args, cwd, **kwargs):
        self.calls += 1
        staging = Path(cwd) / args[args.index('--outDir') + 1]
        staging.mkdir(exist_ok=True)
        (staging / 'partial.js').write_text('x', encoding='utf-8')
        if self.write_index and not self.code:
            (staging / 'index.html').write_text('<html>', encoding='utf-8')
        return SimpleNamespace(returncode=self.code)


@pytest.fixture
def frontend(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, 'find_npm', lambda: 'npm.cmd')
    return make_frontend(tmp_path / 'frontend')


def test_digest_reacts_only_to_relevant_inputs(frontend):
    base = dl.frontend_digest(frontend)
    (frontend / 'dist').mkdir()
    (frontend / 'dist/x.js').write_text('ignored', encoding='utf-8')
    (frontend / 'node_modules/y.js').write_text('ignored', encoding='utf-8')
    (frontend / 'README.md').write_text('ignored', encoding='utf-8')
    assert dl.frontend_digest(frontend) == base
    for relative in ('src/main.tsx', 'public/logo.svg', 'package-lock.json', 'vite.config.ts'):
        path = frontend / relative
        original = path.read_text(encoding='utf-8')
        path.write_text(original + ' changed', encoding='utf-8')
        assert dl.frontend_digest(frontend) != base, relative
        path.write_text(original, encoding='utf-8')
        assert dl.frontend_digest(frontend) == base
    (frontend / 'src/new.tsx').write_text('new file', encoding='utf-8')
    assert dl.frontend_digest(frontend) != base


def test_first_run_builds_then_reuses_then_rebuilds_on_change(frontend, tmp_path):
    log, build = tmp_path / 'build.log', FakeBuild()
    assert dl.ensure_frontend(log, frontend, run=build) is True  # no build yet
    assert (frontend / 'dist/index.html').is_file() and build.calls == 1
    assert not (frontend / '.dist-staging').exists() and not (frontend / '.dist-previous').exists()
    assert dl.ensure_frontend(log, frontend, run=build) is False  # unchanged: reused
    assert build.calls == 1
    (frontend / 'src/main.tsx').write_text('two', encoding='utf-8')
    assert dl.ensure_frontend(log, frontend, run=build) is True
    assert build.calls == 2 and dl.build_is_current(frontend)


def test_failed_build_is_never_valid_and_blocks_opening(frontend, tmp_path):
    log = tmp_path / 'build.log'
    dl.ensure_frontend(log, frontend, run=FakeBuild())
    (frontend / 'src/main.tsx').write_text('broken change', encoding='utf-8')
    with pytest.raises(dl.LauncherError, match='falló'):
        dl.ensure_frontend(log, frontend, run=FakeBuild(code=1))
    assert not dl.build_is_current(frontend)  # the old dist is not presented as valid
    assert not (frontend / '.dist-staging').exists()  # partial output removed
    with pytest.raises(dl.LauncherError):  # the same inputs fail again instead of opening the old build silently
        dl.ensure_frontend(log, frontend, run=FakeBuild(code=1))


def test_build_without_index_is_not_accepted(frontend, tmp_path):
    with pytest.raises(dl.LauncherError):
        dl.ensure_frontend(tmp_path / 'b.log', frontend, run=FakeBuild(write_index=False))
    assert not (frontend / 'dist').exists() and not dl.build_is_current(frontend)


def test_missing_dependencies_explained_and_nothing_run(frontend, tmp_path):
    (frontend / 'node_modules').rmdir()
    build = FakeBuild()
    with pytest.raises(dl.LauncherError, match='CONSTRUIR_FRONTEND'):
        dl.ensure_frontend(tmp_path / 'b.log', frontend, run=build)
    assert build.calls == 0  # never npm install/ci on open


def test_stamp_is_inside_dist_so_a_hand_built_dist_is_rebuilt_once(frontend, tmp_path):
    (frontend / 'dist').mkdir()
    (frontend / 'dist/index.html').write_text('manual build', encoding='utf-8')
    assert not dl.build_is_current(frontend)
    build = FakeBuild()
    assert dl.ensure_frontend(tmp_path / 'b.log', frontend, run=build) is True and build.calls == 1


# ------------------------------------------------------------------------------------------------ lifecycle


class FakeProc:
    _next = 1000

    def __init__(self, name, stop_file=None, stubborn=False):
        FakeProc._next += 1
        self.pid, self.name, self.stop_file, self.stubborn = FakeProc._next, name, stop_file, stubborn
        self.code, self.killed, self.polls = None, False, 0

    def poll(self):
        self.polls += 1
        if self.code is None and self.stop_file and not self.stubborn and Path(self.stop_file).exists():
            self.code = 0
        return self.code

    def wait(self, timeout=None):
        if self.code is None:
            self.code = 0  # the user closes the window
        return self.code

    def kill(self):
        self.killed, self.code = True, -9


class FakeJob:
    def __init__(self):
        self.terminated = False
        self._handle = 1
        self.counts = [1, 1, 0]  # window open for two polls, then the user closes it

    def active(self):
        return self.counts.pop(0) if len(self.counts) > 1 else self.counts[0]

    def add(self, process):
        pass

    def terminate(self):
        self.terminated = True


class Rig:
    """A Launcher wired to doubles; `events` records the order of every start/stop."""

    def __init__(self, tmp_path, kind='sqlite', host_fails=False, stubborn=False, port_busy=False, pg_running=False):
        root = tmp_path / 'instance'
        (root / 'private').mkdir(parents=True, exist_ok=True)
        (root / 'private/service.json').write_text('{}', encoding='utf-8')
        self.events, self.procs, self.errors, self.asked = [], [], [], []
        self.root = root
        self.launcher = dl.Launcher(dl.Instance(root, kind, 8123), python='py', browser='edge')
        launcher = self.launcher
        launcher.spawn = self.spawn
        launcher.identity = lambda pid: 5000 + pid
        launcher.health = lambda url: True
        launcher.make_job = FakeJob
        launcher.resume = lambda proc: self.events.append('window-resume')
        launcher.build_frontend = lambda: self.events.append('build')
        launcher.free = lambda port: not port_busy
        launcher.sleep = lambda seconds: None
        launcher.grace = 1
        launcher.error = self.errors.append
        launcher.ask_wait = lambda text: self.asked.append(text) or self.keep_waiting.pop(0)
        self.keep_waiting = []
        self.host_fails, self.stubborn = host_fails, stubborn
        if kind == 'postgres':
            launcher.start_postgres = lambda r: self.events.append('pg-start')
            launcher.stop_postgres = lambda r: self.events.append('pg-stop')
            launcher.postgres_running = lambda r: pg_running or ('pg-start' in self.events and 'pg-stop' not in self.events)
        self._secrets()

    def _secrets(self):
        import secure_config

        secure_config.load = lambda path: {'DATABASE_URL': 'sqlite://', 'APP_TOKEN': 'x'}

    def spawn(self, args, **kwargs):
        if args[0] == 'py':  # API/workers child
            proc = FakeProc('api', stop_file=self.root / dl.STOP_FILE, stubborn=self.stubborn)
            if self.host_fails:
                proc.code = 3
                (self.root / dl.STATUS_FILE).write_text(
                    json.dumps({'message': 'Esquema incompatible'}), encoding='utf-8'
                )
            else:
                (self.root / dl.STATUS_FILE).write_text(
                    json.dumps({'state': 'running', 'pid': proc.pid, 'token': kwargs['env']['CS_LAUNCH_TOKEN']}),
                    encoding='utf-8',
                )
            self.events.append('api-start')
        else:
            proc = FakeProc('window')
            self.events.append('window-start')
        self.procs.append(proc)
        return proc


@pytest.fixture(autouse=True)
def no_real_secrets(monkeypatch):
    import secure_config

    monkeypatch.setattr(secure_config, 'load', secure_config.load)  # restored after each test


def test_normal_open_close_stops_only_what_it_started_in_order(tmp_path):
    rig = Rig(tmp_path, kind='postgres')
    rig.launcher.acquire = lambda: True
    assert rig.launcher.run() is True
    assert rig.events == ['build', 'pg-start', 'api-start', 'window-start', 'window-resume', 'pg-stop']
    api = rig.procs[0]
    assert api.code == 0 and not api.killed  # orderly stop through the stop file
    assert rig.launcher.job.terminated  # window leftovers released through our own job
    assert not (rig.root / dl.RUN_FILE).exists() and rig.errors == []


def test_failure_midway_closes_components_already_started(tmp_path):
    rig = Rig(tmp_path, kind='postgres', host_fails=True)
    rig.launcher.acquire = lambda: True
    assert rig.launcher.run() is False
    assert rig.events == [
        'build',
        'pg-start',
        'api-start',
        'pg-stop',
    ]  # own PostgreSQL stopped even though the API failed
    assert 'Esquema incompatible' in rig.errors[0]
    assert not any(e == 'window-start' for e in rig.events)


def test_window_closure_follows_the_job_not_the_launching_process(tmp_path):
    rig = Rig(tmp_path)
    rig.launcher.acquire = lambda: True
    original = rig.spawn

    def browser_hands_off(args, **kwargs):
        proc = original(args, **kwargs)
        if args[0] == 'edge':
            proc.code = 0  # the launched process exits at once, as Edge does
        return proc

    rig.launcher.spawn = browser_hands_off
    sleeps = []
    rig.launcher.sleep = sleeps.append
    assert rig.launcher.run() is True
    assert len(sleeps) >= 2  # it kept waiting while the job still had live processes


def test_preexisting_postgres_is_not_adopted_or_stopped(tmp_path):
    rig = Rig(tmp_path, kind='postgres', pg_running=True)
    rig.launcher.acquire = lambda: True
    assert rig.launcher.run() is False
    assert rig.events == ['build'] and 'pg-stop' not in rig.events and 'pg-start' not in rig.events
    assert 'no lo inició esta apertura' in rig.errors[0]


def test_busy_port_aborts_before_starting_anything(tmp_path):
    rig = Rig(tmp_path, port_busy=True)
    rig.launcher.acquire = lambda: True
    assert rig.launcher.run() is False
    assert rig.procs == [] and 'otro programa' in rig.errors[0]


def test_duplicate_open_is_refused_while_the_first_holds_the_lock(tmp_path):
    first, second = Rig(tmp_path), Rig(tmp_path)
    assert first.launcher.acquire() is True
    try:
        second.launcher.error = second.errors.append
        assert second.launcher.run() is False
        assert second.procs == [] and 'ya está abierta' in second.errors[0]
        assert second.events == []  # it did not build, start nor stop anything of the first opening
    finally:
        first.launcher.release()
    assert second.launcher.acquire() is True  # released after the first one closes
    second.launcher.release()


def test_closing_waits_then_interrupts_only_on_confirmation(tmp_path):
    rig = Rig(tmp_path, stubborn=True)
    rig.launcher.acquire = lambda: True
    rig.keep_waiting = [True, False]  # wait once more, then confirm the interruption
    assert rig.launcher.run() is True
    assert len(rig.asked) == 2 and rig.procs[0].killed
    assert rig.procs[0].polls > 2


def test_recover_kills_only_verified_orphans(tmp_path):
    rig = Rig(tmp_path)
    launcher = rig.launcher
    state = {
        'postgres_owned': False,
        'components': [
            {'name': 'api', 'pid': 111, 'created': 5111},  # same pid and start time: ours
            {'name': 'ventana', 'pid': 222, 'created': 1},  # pid reused by another program
            {'name': 'otro', 'pid': 333, 'created': None},  # never verified
        ],
    }
    (rig.root / dl.RUN_FILE).write_text(json.dumps(state), encoding='utf-8')
    killed = []
    launcher.recover(kill=killed.append)
    assert killed == [111]
    assert not (rig.root / dl.RUN_FILE).exists()


def test_run_state_records_owned_processes(tmp_path):
    rig = Rig(tmp_path)
    rig.launcher.acquire = lambda: True
    seen = []
    original = rig.launcher.open_window

    def spy():
        seen.append(json.loads((rig.root / dl.RUN_FILE).read_text(encoding='utf-8')))
        return original()

    rig.launcher.open_window = spy
    rig.launcher.run()
    assert [c['name'] for c in seen[0]['components']] == ['api'] and seen[0]['components'][0]['created']


# ------------------------------------------------------------------------------------------------ agent jobs

INTERRUPTED = 'Interrumpido al cerrar ContaSuite'  # the text backend/app/agent_jobs.py writes (tested there on a database)


class FakeJobs:
    """The running jobs of the instance: what the launcher asks, and what it marks failed."""

    def __init__(self, rig, jobs, finish_after=None):
        self.rig = rig
        self.status = {j['id']: 'running' for j in jobs}
        self.kinds = {j['id']: j['kind'] for j in jobs}
        self.error = {}
        self.finish_after = finish_after  # consultations before the agent finishes by itself
        self.queries = 0
        self.interrupted_when = None

    def running(self):
        self.queries += 1
        if self.finish_after is not None and self.queries > self.finish_after:
            self.status = {k: 'completed' for k in self.status}
        return [{'id': k, 'kind': self.kinds[k], 'company_id': 'c1'} for k, v in self.status.items() if v == 'running']

    def interrupt(self, ids):
        agent = next(o.proc for o in self.rig.launcher.owned if o.name == 'agente')
        self.interrupted_when = {
            'agent_already_stopped': agent.killed,
            'server_still_up': not (self.rig.root / dl.STOP_FILE).exists(),
        }
        for i in ids:
            if self.status.get(i) == 'running':
                self.status[i], self.error[i] = 'failed', INTERRUPTED
        return list(ids)


def busy_rig(tmp_path, jobs, finish_after=None, answers=()):
    rig = Rig(tmp_path)
    launcher = rig.launcher
    launcher.with_agent = True
    launcher.job_poll = 0.5
    launcher.host_job, launcher.agent_job = FakeJob(), FakeJob()
    api = FakeProc('api', stop_file=rig.root / dl.STOP_FILE)
    agent = FakeProc('agente')
    launcher.owned += [dl.Owned('api', api, 1), dl.Owned('agente', agent, 2)]
    rig.keep_waiting = list(answers)
    rig.db = FakeJobs(rig, jobs, finish_after)
    launcher.agent_jobs, launcher.interrupt_jobs = rig.db.running, rig.db.interrupt
    rig.api, rig.agent = api, agent
    return rig


SCAN = {'id': 'job-1', 'kind': 'scan_folder'}


def test_closing_with_a_busy_agent_asks_before_stopping_it(tmp_path):
    rig = busy_rig(tmp_path, [SCAN], answers=[False])
    rig.launcher.stop_all()
    assert len(rig.asked) == 1 and 'agente local sigue trabajando' in rig.asked[0]
    assert 'análisis de carpeta' in rig.asked[0] and '¿Esperar' in rig.asked[0]


def test_interrupting_marks_the_job_failed_before_the_server_stops(tmp_path):
    rig = busy_rig(tmp_path, [SCAN, {'id': 'job-2', 'kind': 'sat_declaraciones'}], answers=[False])
    rig.launcher.stop_all()
    assert rig.db.status == {'job-1': 'failed', 'job-2': 'failed'}
    assert rig.db.error == {'job-1': INTERRUPTED, 'job-2': INTERRUPTED}
    assert 'descarga de declaraciones del SAT' in rig.asked[0]
    assert rig.db.interrupted_when == {'agent_already_stopped': True, 'server_still_up': True}
    assert rig.agent.killed and rig.api.code == 0  # the agent stopped, the server stopped in order afterwards


def test_waiting_lets_the_job_finish_and_marks_nothing(tmp_path):
    rig = busy_rig(tmp_path, [SCAN], finish_after=2, answers=[True])
    rig.launcher.stop_all()
    assert len(rig.asked) == 1  # one question; it kept waiting until the agent was idle
    assert rig.db.status == {'job-1': 'completed'} and rig.db.error == {} and rig.db.interrupted_when is None
    assert rig.agent.killed and rig.api.code == 0


def test_it_asks_again_after_the_grace_period_while_the_job_keeps_running(tmp_path):
    rig = busy_rig(tmp_path, [SCAN], answers=[True, False])  # wait; later, interrupt
    rig.launcher.stop_all()
    assert len(rig.asked) == 2 and rig.db.status == {'job-1': 'failed'}


def test_an_idle_agent_is_stopped_without_asking(tmp_path):
    rig = busy_rig(tmp_path, [])
    rig.launcher.stop_all()
    assert rig.asked == [] and rig.agent.killed and rig.db.interrupted_when is None


def test_not_being_able_to_ask_the_server_never_blocks_the_closing(tmp_path):
    rig = busy_rig(tmp_path, [SCAN])

    def broken():
        raise dl.LauncherError('sin consulta')

    rig.launcher.agent_jobs = broken
    rig.launcher.stop_all()
    assert rig.asked == [] and rig.agent.killed and rig.api.code == 0


def test_without_an_agent_nothing_is_asked(tmp_path):
    rig = Rig(tmp_path)
    rig.launcher.agent_jobs = lambda: pytest.fail('there is no agent to ask about')
    rig.launcher.acquire = lambda: True
    assert rig.launcher.run() is True and rig.asked == []


def test_jobs_are_reached_through_an_internal_child_never_an_endpoint(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    rig.launcher.python = 'py'
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=b'["job-1"]')

    monkeypatch.setattr(dl.subprocess, 'run', fake_run)
    assert rig.launcher.interrupt_agent_jobs(['job-1', 'job-2']) == ['job-1']
    args, kwargs = calls[0]
    assert args[-2:] == ['--instance', str(rig.root)] and '--jobs' in args and args[args.index('--jobs') + 1] == 'interrupt'
    assert args.count('--job-id') == 2 and 'job-1' in args and 'job-2' in args
    assert kwargs['env']['PYTHON_DOTENV_DISABLED'] == '1' and kwargs['env']['DATABASE_URL'] == 'sqlite://'  # own config
    assert rig.launcher.running_agent_jobs() == ['job-1'] and calls[1][0][calls[1][0].index('--jobs') + 1] == 'list'

    monkeypatch.setattr(dl.subprocess, 'run', lambda args, **kw: SimpleNamespace(returncode=3, stdout=b''))
    with pytest.raises(dl.LauncherError, match='trabajos del agente'):
        rig.launcher.running_agent_jobs()


# ------------------------------------------------------------------------------------------------ instance


def test_instance_roundtrip_and_incomplete_folder_is_kept(tmp_path):
    root = tmp_path / 'dev'
    root.mkdir()
    (root / 'orphan.txt').write_text('partial creation', encoding='utf-8')
    with pytest.raises(dl.LauncherError, match='no está completa'):
        dl.Instance.create(root, python='py')
    assert (root / 'orphan.txt').is_file()  # nothing removed or reinitialised
    (root / 'orphan.txt').unlink()
    assert dl.Instance.open(root) is None
    (root / 'INSTANCE.json').write_text(json.dumps({'format': dl.INSTANCE_FORMAT, 'port': 8111}), encoding='utf-8')
    instance = dl.Instance.open(root)
    assert instance.port == 8111 and instance.url == 'http://127.0.0.1:8111' and instance.kind == 'sqlite'


def test_ports_avoid_reserved_instances():
    assert dl.choose_port(lambda port: True) == 8100
    assert not set(dl.PORT_RANGE) & {8000, 8062, 8072, 8090, 8099}
    with pytest.raises(dl.LauncherError):
        dl.choose_port(lambda port: False)


def test_app_python_must_import_the_backend(tmp_path):
    good, broken = tmp_path / 'good.exe', tmp_path / 'broken.exe'
    good.write_text('', encoding='utf-8')
    broken.write_text('', encoding='utf-8')
    assert dl.find_app_python([broken, good], check=lambda p: Path(p) == good) == good
    with pytest.raises(dl.LauncherError, match='CONTA_PYTHON'):
        dl.find_app_python([broken], check=lambda p: False)


def test_child_environment_never_falls_back_to_dotenv(tmp_path):
    env = dl.host_environment({'DATABASE_URL': 'sqlite://', 'APP_TOKEN': 'a'}, tmp_path)
    assert (
        env['PYTHON_DOTENV_DISABLED'] == '1'
        and env['SEED_DEMO'] == 'false'
        and env['DATA_DIR'] == str(tmp_path / 'data')
    )
