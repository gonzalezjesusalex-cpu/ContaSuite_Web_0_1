"""Verify the Alembic chain on a throwaway PostgreSQL cluster (never a real instance).

Usage: python scripts/verify_postgres.py --bin <PostgreSQL bin folder> --work <new empty folder> [--port 55499]

Creates its own cluster in --work and checks: a new installation; an update from cs_0006 with data (refused
without a backup, idempotent, roles converted, responsible accountant kept unassigned); that the pg_dump backup
restores to the previous version, which the current code reports as pending; and the application on PostgreSQL
(bootstrap, company, linked agent job). The cluster is stopped at the end.
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ARGS = argparse.ArgumentParser()
ARGS.add_argument('--bin', type=Path, required=True)
ARGS.add_argument('--work', type=Path, required=True)
ARGS.add_argument('--port', default='55499')
OPTIONS = ARGS.parse_args()
BIN = OPTIONS.bin.resolve()
WORK = OPTIONS.work.resolve()
DATA = WORK / 'data'
PORT = OPTIONS.port
URL = 'postgresql+psycopg://postgres@127.0.0.1:' + PORT + '/'


def run(*cmd, **kw):
    print('$', ' '.join(str(c) for c in cmd[:3]), flush=True)
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def start():
    if WORK.exists() and any(WORK.iterdir()):
        raise SystemExit('--work debe ser una carpeta nueva o vacía.')
    WORK.mkdir(parents=True, exist_ok=True)
    run(
        BIN / 'initdb.exe',
        '-D',
        DATA,
        '-U',
        'postgres',
        '-A',
        'trust',
        '-E',
        'UTF8',
        '--no-locale',
        capture_output=True,
    )
    run(
        BIN / 'pg_ctl.exe',
        '-D',
        DATA,
        '-o',
        '-p ' + PORT + ' -h 127.0.0.1',
        '-l',
        WORK / 'pg.log',
        '-w',
        'start',
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    for name in ['cs_new', 'cs_upgrade']:
        run(BIN / 'createdb.exe', '-h', '127.0.0.1', '-p', PORT, '-U', 'postgres', name)


def schema_admin(db, *args):
    env = dict(os.environ, DATABASE_URL=URL + db, PYTHON_DOTENV_DISABLED='1')
    out = subprocess.run(
        [sys.executable, ROOT / 'scripts/schema_admin.py', '--data-dir', WORK / ('files-' + db), *args],
        env=env,
        capture_output=True,
        text=True,
    )
    print(out.stdout.strip(), out.stderr.strip()[-600:])
    return out.returncode


def fill(conn, table, values):
    """Insert one row giving any NOT NULL column without default a neutral value."""
    from sqlalchemy import Boolean, DateTime, Integer, JSON, MetaData, Table, insert

    t = Table(table, MetaData(), autoload_with=conn)
    row = {}
    for c in t.columns:
        if c.name in values:
            row[c.name] = values[c.name]
        elif not c.nullable and c.server_default is None:
            if isinstance(c.type, Boolean):
                row[c.name] = False
            elif isinstance(c.type, DateTime):
                row[c.name] = datetime.now(timezone.utc)
            elif isinstance(c.type, Integer):
                row[c.name] = 0
            elif isinstance(c.type, JSON) or 'JSON' in str(c.type).upper():
                row[c.name] = {}
            else:
                row[c.name] = str(uuid4()) if c.name == 'id' else 'x'
    conn.execute(insert(t).values(**row))


def upgrade_with_data():
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    os.environ['DATABASE_URL'] = URL + 'cs_upgrade'
    os.environ['DATA_DIR'] = str(WORK / 'files-cs_upgrade')
    sys.path.insert(0, str(ROOT / 'backend'))
    from sqlalchemy import create_engine, text
    from app.storage.migrate import _upgrade

    engine = create_engine(URL + 'cs_upgrade')
    _upgrade(engine, 'cs_0006')
    admin, aux = str(uuid4()), str(uuid4())
    company = str(uuid4())
    with engine.begin() as conn:
        fill(conn, 'user_accounts', {'id': admin, 'username': 'admin', 'display_name': 'Admin', 'admin': True})
        fill(conn, 'user_accounts', {'id': aux, 'username': 'colab', 'display_name': 'Ana Pérez', 'admin': False})
        fill(conn, 'companies', {'id': company, 'name': 'Empresa PG', 'rfc': 'EPG010101AA1', 'accountant': 'Ana Pérez'})
        fill(conn, 'user_company_grants', {'user_id': aux, 'company_id': company, 'access': 'write'})
    engine.dispose()
    backup = WORK / 'antes.dump'
    run(BIN / 'pg_dump.exe', '-h', '127.0.0.1', '-p', PORT, '-U', 'postgres', '-Fc', '-f', backup, 'cs_upgrade')
    assert schema_admin('cs_upgrade', '--apply') != 0, 'apply without backup must be refused'
    assert schema_admin('cs_upgrade', '--apply', '--backup', backup) == 0
    assert schema_admin('cs_upgrade', '--apply', '--backup', backup) == 0, 'second apply must be a no-op'
    engine = create_engine(URL + 'cs_upgrade')
    with engine.connect() as conn:
        roles = dict(conn.execute(text('SELECT username, role FROM user_accounts')).all())
        legacy = conn.execute(text('SELECT accountant_legacy, accountant_id FROM companies')).one()
        checks = conn.execute(text("SELECT conname FROM pg_constraint WHERE conname = 'ck_user_account_role'")).all()
        version = conn.execute(text('SELECT version_num FROM alembic_version')).scalar()
    engine.dispose()
    print('roles', roles, 'legacy', tuple(legacy), 'check', bool(checks), 'version', version)
    assert roles == {'admin': 'admin', 'colab': 'auxiliar'}
    assert legacy[0] == 'Ana Pérez' and legacy[1] is None  # nobody is assigned automatically
    assert checks and version == 'cs_0022_vault_master_password'
    # The backup restores into a fresh database (what an operator would do to roll back).
    run(BIN / 'createdb.exe', '-h', '127.0.0.1', '-p', PORT, '-U', 'postgres', 'cs_restored')
    run(BIN / 'pg_restore.exe', '-h', '127.0.0.1', '-p', PORT, '-U', 'postgres', '-d', 'cs_restored', backup)
    # The restored database is the previous version: the current code reports it as pending and never migrates it.
    assert schema_admin('cs_restored', '--status') != 0


def api_smoke():
    """The application itself on PostgreSQL: bootstrap, roles, company with CSF fields, agent pairing."""
    code = r'''
import os, sys
sys.path.insert(0, sys.argv[1])
from fastapi.testclient import TestClient
from app.main import app
A = {"Authorization": "Bearer " + os.environ["APP_TOKEN"]}
with TestClient(app) as c:
    r = c.post("/api/auth/bootstrap", headers=A, json={"username": "admin", "display_name": "Admin", "password": "Clave-de-prueba-123"})
    assert r.status_code == 201, r.text
    r = c.post("/api/auth/login", json={"username": "admin", "password": "Clave-de-prueba-123"})
    c.headers["X-CSRF-Token"] = c.cookies.get("contasuite_csrf") or [v for k, v in c.cookies.items() if "csrf" in k][0]
    r = c.post("/api/companies", json={"name": "Empresa PG", "rfc": "EPG010101AA1", "idcif": "12345678", "folder": "C:\\Empresas\\PG"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert c.put("/api/agent-links/roots", json={"paths": ["C:\\Empresas"]}).status_code == 200
    code = c.post("/api/agent-links/code").json()["code"]
    token = c.post("/api/agent/pair", json={"code": code, "agent_id": "pg-agent", "machine": "PC"}).json()["token"]
    B = {"Authorization": "Bearer " + token}
    assert c.post("/api/agent/heartbeat", headers=B, json={"id": "pg-agent", "capabilities": ["scan_folder"]}).status_code == 200
    job = c.post("/api/jobs", json={"company_id": cid, "kind": "scan_folder"})
    assert job.status_code == 201, job.text
    claimed = c.post("/api/agent/pg-agent/claim", headers=B).json()
    assert claimed["id"] == job.json()["id"]
    assert c.post("/api/agent/jobs/" + claimed["id"] + "/result", headers=B, json={"agent_id": "pg-agent", "status": "completed", "result": {"files": []}}).status_code == 200
    hist = c.get("/api/companies/" + cid + "/history")
    assert hist.status_code == 200, hist.text
    print("API smoke on PostgreSQL: OK", len(hist.json()), "history rows")
'''
    env = dict(
        os.environ,
        DATABASE_URL=URL + 'cs_new',
        PYTHON_DOTENV_DISABLED='1',
        DATA_DIR=str(WORK / 'files-cs_new'),
        APP_TOKEN='pg-verify-app-token-only-0123456789',
        SEED_DEMO='false',
        CS_STORAGE_ALLOWED_ROOTS='[]',
        CS_STORAGE_SMB_ALLOWED_ROOTS='[]',
    )
    env.pop('AGENT_TOKEN', None)
    out = subprocess.run(
        [sys.executable, '-c', code, str(ROOT / 'backend')],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(ROOT / 'backend'),
    )
    print(out.stdout.strip(), out.stderr.strip()[-1500:])
    assert out.returncode == 0


try:
    start()
    assert schema_admin('cs_new', '--new', '--apply') == 0
    upgrade_with_data()
    api_smoke()
    print('PASS: PostgreSQL 17')
finally:
    subprocess.run([BIN / 'pg_ctl.exe', '-D', DATA, 'stop', '-m', 'fast'], capture_output=True)
