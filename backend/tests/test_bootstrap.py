import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

spec=importlib.util.spec_from_file_location('bootstrap',Path(__file__).resolve().parents[2]/'scripts/bootstrap_windows.py')
bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)

def test_python_315_is_rejected(monkeypatch):
    monkeypatch.setattr(bootstrap.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout='[3,15,64]',returncode=0))
    assert not bootstrap.probe(['py','-3'])

def test_python_selection_prefers_312(monkeypatch):
    seen=[]
    def probe(command):seen.append(command);return command==['py','-3.12']
    monkeypatch.setattr(bootstrap,'probe',probe)
    assert bootstrap.select_python()==['py','-3.12']
    assert seen==[['py','-3.12']]

def test_python_selection_falls_back_to_311(monkeypatch):
    monkeypatch.setattr(bootstrap,'probe',lambda command:command==['py','-3.11'])
    assert bootstrap.select_python()==['py','-3.11']

def test_missing_supported_python_has_clear_error(monkeypatch):
    monkeypatch.setattr(bootstrap,'probe',lambda _:False)
    with pytest.raises(RuntimeError,match='3.12'):bootstrap.select_python()

def test_portable_profile_excludes_postgres_unless_env_requires_it(tmp_path,monkeypatch):
    monkeypatch.setattr(bootstrap,'ROOT',tmp_path)
    assert bootstrap.profile(True)=='base'
    assert bootstrap.profile(False)=='postgres'
    (tmp_path/'.env').write_text('DATABASE_URL=postgresql+psycopg://example\n')
    assert bootstrap.profile(True)=='postgres'
    (tmp_path/'.env').write_text('DATABASE_URL=sqlite:///data/example.db\n')
    assert bootstrap.profile(False)=='base'
