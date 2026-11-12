import importlib.util
import json
import sqlite3
import hashlib
from pathlib import Path
from test_api import client  # Keep database imports isolated from real installation.


def script(name):
    path=Path(__file__).resolve().parents[2]/'scripts'/name
    spec=importlib.util.spec_from_file_location(name.replace('.','_'),path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_build(root):
    dist=root/'frontend'/'dist'
    (dist/'assets').mkdir(parents=True)
    (dist/'index.html').write_text('<html>synthetic</html>',encoding='utf-8')
    (dist/'assets'/'test.js').write_text('/auth/bootstrap /storage/connector/sources /storage/dashboard',encoding='utf-8')
    script('stamp_build.py').stamp(root)
    return dist


def test_preflight_is_readonly_private_and_verifies_build(tmp_path,monkeypatch):
    preflight=script('visit_check.py')
    dist=fake_build(tmp_path)
    database=tmp_path/'sample.db'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE alembic_version(version_num TEXT)')
        connection.execute("INSERT INTO alembic_version VALUES('cs_storage_0004')")
        connection.execute('CREATE TABLE identity_state(initialized BOOLEAN)')
        connection.execute('INSERT INTO identity_state VALUES(1)')
    secret='Synthetic-preflight-secret-token-only'
    env='DATABASE_URL=sqlite:///'+str(database)+'\nAPP_TOKEN='+secret+'\n'
    (tmp_path/'.env').write_text(env,encoding='utf-8')
    monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.delenv('APP_TOKEN',raising=False)
    before=hashlib.sha256(database.read_bytes()).hexdigest()
    result=preflight.inspect_project(tmp_path)
    assert result['ready_for_local_demo']
    assert secret not in json.dumps(result) and str(tmp_path) not in json.dumps(result)
    assert hashlib.sha256(database.read_bytes()).hexdigest()==before
    (dist/'assets'/'test.js').write_text('changed',encoding='utf-8')
    assert not preflight.inspect_project(tmp_path)['ready_for_local_demo']


def test_preflight_does_not_contact_postgresql_or_unc(tmp_path,monkeypatch):
    preflight=script('visit_check.py')
    fake_build(tmp_path)
    def forbidden(*args,**kwargs):raise AssertionError('No database may be probed')
    monkeypatch.setattr(sqlite3,'connect',forbidden)
    monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.delenv('APP_TOKEN',raising=False)
    for url in ['postgresql://user:Secret-not-for-report@server.invalid/db','sqlite://///server.invalid/share/db.sqlite']:
        (tmp_path/'.env').write_text('DATABASE_URL='+url+'\nAPP_TOKEN=Synthetic-preflight-token-42\n',encoding='utf-8')
        report=preflight.inspect_project(tmp_path)
        assert 'Secret-not-for-report' not in json.dumps(report)
        assert next(c for c in report['checks'] if c['check']=='database_schema')['state']=='pending'


def test_new_installation_is_empty_and_existing_settings_are_preserved(tmp_path,monkeypatch):
    setup=script('setup_windows.py')
    (tmp_path/'agent').mkdir()
    fake_build(tmp_path)
    monkeypatch.setattr(setup,'root',tmp_path)
    setup.configure(portable=True)
    original=(tmp_path/'.env').read_bytes()
    agent=(tmp_path/'agent'/'config.json').read_bytes()
    assert b'SEED_DEMO=false' in original and b'CS_STORAGE_ALLOWED_ROOTS=[]' in original
    setup.configure(portable=True)
    assert (tmp_path/'.env').read_bytes()==original
    assert (tmp_path/'agent'/'config.json').read_bytes()==agent
