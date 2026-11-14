"""CS_PORT is the single source of the API port; each launcher keeps its own documented default."""

import json
import re
from pathlib import Path

import pytest

from test_visit_readiness import fake_build, script

ROOT = Path(__file__).resolve().parents[2]


def test_default_port_reads_cs_port_and_validates(monkeypatch):
    runtime = script('service_runtime.py')
    monkeypatch.delenv('CS_PORT', raising=False)
    assert runtime.default_port() == runtime.SERVICE_PORT == 8062
    assert runtime.default_port(runtime.LEGACY_PORT) == 8000
    monkeypatch.setenv('CS_PORT', '9123')
    assert runtime.default_port() == 9123 and runtime.default_port(8000) == 9123
    for invalid in ('0', '70000', 'abc', '-5', '80.5'):
        monkeypatch.setenv('CS_PORT', invalid)
        with pytest.raises(ValueError, match='CS_PORT'):
            runtime.default_port()


def test_old_instance_launchers_keep_8000_unless_cs_port(tmp_path, monkeypatch):
    setup = script('setup_windows.py')
    monkeypatch.delenv('CS_PORT', raising=False)
    assert setup.launcher_port() == 8000
    (tmp_path / 'agent').mkdir()
    fake_build(tmp_path)
    monkeypatch.setattr(setup, 'root', tmp_path)
    monkeypatch.setenv('CS_PORT', '8111')
    setup.configure(portable=True)
    assert json.loads((tmp_path / 'agent' / 'config.json').read_text(encoding='utf-8'))['api_url'] == (
        'http://127.0.0.1:8111'
    )
    monkeypatch.setenv('CS_PORT', 'x')
    with pytest.raises(SystemExit, match='CS_PORT'):
        setup.launcher_port()


def test_service_cli_defaults_to_cs_port_or_8062(monkeypatch):
    for name in ('service_runtime.py', 'windows_service.py', 'service_admin.py'):
        text = (ROOT / 'scripts' / name).read_text(encoding='utf-8')
        assert "add_argument('--port', type=int, default=None" in text, name
        assert 'default_port()' in text, name


def test_development_tooling_uses_cs_port_with_dedicated_8090():
    dev = (ROOT / 'scripts' / 'dev.mjs').read_text(encoding='utf-8')
    vite = (ROOT / 'frontend' / 'vite.config.ts').read_text(encoding='utf-8')
    assert "process.env.CS_PORT||'8090'" in dev and "process.env.CS_PORT || '8090'" in vite
    code = '\n'.join(line for line in dev.splitlines() if not line.lstrip().startswith('//'))
    assert not re.search(r'\b8000\b', code) and not re.search(r'127\.0\.0\.1:8000', vite)
