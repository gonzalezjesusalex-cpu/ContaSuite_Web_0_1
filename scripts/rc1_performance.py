"""Measure the real dashboard against 25,271 synthetic PostgreSQL documents only."""

import argparse
import json
import os
import sys
import time
import statistics
from pathlib import Path
from release_lab import configuration
from integration_runtime import ROOT, RUN, call


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if not args.run_id.isalnum() or len(args.run_id) > 12:
        parser.error('Short alphanumeric run id required')
    _, previous, env = configuration()
    import psycopg
    from psycopg import sql

    name = 'contasuite_rc1_perf_' + args.run_id
    with psycopg.connect(
        host='127.0.0.1',
        port=previous['port'],
        user='recovery_test',
        password=previous['password'],
        dbname='postgres',
        autocommit=True,
    ) as db:
        assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve() == RUN / 'cluster'
        assert not db.execute('SELECT 1 FROM pg_database WHERE datname=%s', (name,)).fetchone()
        db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    work = ROOT / '.qa' / ('rc1-performance-' + args.run_id)
    work.mkdir(exist_ok=False)
    env.update(DATABASE_URL=env['DATABASE_URL'].rsplit('/', 1)[0] + '/' + name, DATA_DIR=str(work / 'data'))
    call([sys.executable, '-B', ROOT / 'scripts/schema_admin.py', '--data-dir', work / 'data', '--apply', '--new'], env)
    os.environ.update(env)
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.database import engine, SessionLocal
    from app.models import Document, Company
    from app.security import Principal
    from app.integral_dashboard import dashboard
    from sqlalchemy import event, insert

    with SessionLocal.begin() as db:
        db.add(
            Company(
                id='synthetic-company',
                name='Synthetic benchmark',
                rfc='AAA010101AAA',
                regime='Synthetic',
                accountant='Synthetic',
            )
        )
        db.flush()
        db.execute(
            insert(Document),
            [
                dict(
                    id=f'synthetic-document-{i}',
                    name=f'synthetic-{i}.pdf',
                    company_id='synthetic-company' if i < 10017 else None,
                    size=100,
                    managed=True,
                    storage_revision=0,
                )
                for i in range(25271)
            ],
        )
    count = [0]

    def statement(*args):
        count[0] += 1

    event.listen(engine, 'before_cursor_execute', statement)
    timings = []
    queries = []
    sizes = []
    for _ in range(3):
        count[0] = 0
        start = time.perf_counter()
        with SessionLocal() as db:
            report = dashboard(db, Principal('synthetic-admin', 'Synthetic', True), 2026, 11)
        timings.append(round((time.perf_counter() - start) * 1000, 2))
        queries.append(count[0])
        sizes.append(len(json.dumps(report, default=str).encode()))
        assert report['documents']['indexed'] == 25271 and report['documents']['associated'] == 10017
    result = {
        'synthetic_only': True,
        'database_backend': 'PostgreSQL',
        'documents': 25271,
        'associated': 10017,
        'unassociated': 15254,
        'dashboard_ms': timings,
        'dashboard_median_ms': statistics.median(timings),
        'query_counts': queries,
        'response_bytes': sizes,
        'real_PDF_SMB_concurrency_measured': False,
        'note': 'Synthetic catalog rows; no real content, versions or UUID conflicts; not a pilot acceptance benchmark',
    }
    (work / 'results.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
