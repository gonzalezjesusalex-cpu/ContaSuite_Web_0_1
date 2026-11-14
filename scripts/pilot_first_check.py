"""Private pilot checks. Print counts/status only; never echo credentials or fiscal metadata."""

import sys
import json
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pilot_first import RUN, DATABASE, configuration
from integration_runtime import BIN, call


def main():
    mode = sys.argv[1]
    c, env = configuration()
    import psycopg
    import httpx
    from psycopg import sql

    credentials = dict(
        host='127.0.0.1', port=c['port'], user='pilot_local', password=c['db_password'], connect_timeout=5
    )
    with psycopg.connect(**credentials, dbname=DATABASE) as db:
        assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve() == RUN / 'cluster'
        assert db.execute('SHOW listen_addresses').fetchone()[0] == '127.0.0.1'
        assert db.execute('SELECT count(*) FROM companies').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM documents').fetchone()[0] == 0
    access = json.loads((RUN / 'access.json').read_text())
    base = 'http://127.0.0.1:8062'
    with httpx.Client(timeout=30) as client:
        assert client.get(base + '/api/pilot-batches').status_code == 401
        assert (
            client.post(
                base + '/api/auth/login', json={'username': access['username'], 'password': access['password']}
            ).status_code
            == 200
        )
        response = client.get(base + '/api/pilot-batches')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store, private'
        value = response.json()['analysis']
        assert value and value['confirmation_enabled'] is False
        assert client.get(base + '/api/pilot-batches/' + value['id'] + '/rows?offset=0&limit=50').status_code == 200
        assert client.get(base + '/api/pilot-batches/' + value['id'] + '/rows?limit=1000').status_code == 422
        csrf = client.cookies.get('contasuite_csrf', '')
        assert (
            client.post(
                base + '/api/company-imports/' + value['id'] + '/confirm',
                headers={'Origin': base, 'X-CSRF-Token': csrf},
                json={'confirmed': True},
            ).status_code
            == 404
        )
        assert client.get(base + '/api/health', headers={'Host': 'unapproved.example'}).status_code == 400
    report = {
        'http_private_preview': 'passed',
        'unauthenticated': 401,
        'oversized_page': 422,
        'legacy_confirm': 404,
        'unapproved_host': 400,
        'companies': 0,
        'documents': 0,
        'external_network_used': False,
    }
    if mode in ('baseline', 'final'):
        target = 'contasuite_pilot_first_' + ('baseline_restore' if mode == 'baseline' else 'preview_restore')
        with psycopg.connect(**credentials, dbname='postgres', autocommit=True) as db:
            assert not db.execute('SELECT 1 FROM pg_database WHERE datname=%s', (target,)).fetchone(), (
                'Refuse existing restore target'
            )
            db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(target)))
        cli = env.copy()
        cli.update(PGHOST='127.0.0.1', PGPORT=str(c['port']), PGUSER='pilot_local', PGPASSWORD=c['db_password'])
        dump = RUN / ('before-analysis.dump' if mode == 'baseline' else 'after-analysis.dump')
        if mode == 'final':
            assert value['status'] == 'preview', 'Wait for analysis to finish before stable backup'
            call([BIN / 'pg_dump.exe', '-Fc', '--file', dump, DATABASE], cli)
        call([BIN / 'pg_restore.exe', '--exit-on-error', '--dbname', target, dump], cli)
        with psycopg.connect(**credentials, dbname=target) as db:
            assert db.execute('SELECT count(*) FROM companies').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM documents').fetchone()[0] == 0
            restored = db.execute('SELECT count(*) FROM reconcile_rows').fetchone()[0]
            if mode == 'baseline':
                assert restored == 0
            else:
                assert restored == value['summary']['total']
        report['restored_staging_rows'] = restored
        report['backup_sha256'] = hashlib.sha256(dump.read_bytes()).hexdigest()
        if mode == 'final':

            def staging_hash(database):
                digest = hashlib.sha256()
                with psycopg.connect(**credentials, dbname=database) as connection:
                    for table, order in [
                        ('reconcile_sessions', 'id'),
                        ('reconcile_rows', 'session_id,number'),
                        ('reconcile_history', 'id'),
                    ]:
                        digest.update(table.encode())
                        with connection.cursor(name='verify_' + table) as cursor:
                            cursor.execute(
                                sql.SQL('SELECT row_to_json(t) FROM {} t ORDER BY ' + order).format(
                                    sql.Identifier(table)
                                )
                            )
                            for row in cursor:
                                digest.update(
                                    json.dumps(row[0], sort_keys=True, default=str, separators=(',', ':')).encode()
                                )
                return digest.hexdigest()

            source_hash = staging_hash(DATABASE)
            assert source_hash == staging_hash(target)
            report['restored_staging_content_sha256'] = source_hash
    (RUN / ('checks-' + mode + '.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:  # noqa: BLE001 - top-level handler: exits non-zero without printing secrets or internal messages
        print('Private pilot validation stopped; error_class=' + type(error).__name__, flush=True)
        raise SystemExit(1) from None
