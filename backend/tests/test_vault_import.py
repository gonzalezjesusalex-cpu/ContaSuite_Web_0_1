"""Renovación del gestor de contraseñas, fase 4: import in three steps (spec, section 6), template and export."""

import io
import json

from openpyxl import Workbook, load_workbook
from sqlalchemy import select, update

from sat_fixtures import pair
from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import setup
from app.credential_models import audit, certificates, credentials, import_templates
from app.database import SessionLocal
from app.models import Company

RFC = 'SSI260101AB1'
OTHER = 'OTR260101AB1'
MASTER = 'Maestra-Sintetica-2026!'
HEADERS = [
    'NO.',
    'EMPRESA',
    'RFC',
    'REGISTRO PATRONAL',
    'NIVEL',
    'Contraseña',
    'FIEL EMPRESA',
    'FIEL REPRE',
    'SELLO DIGITAL',
    'INFONAVIT',
    'Contraseña certificado IMSS',
    'SIPARE',
    'CORREO',
]


def book(sheets):
    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        sheet = wb.create_sheet(title)
        for r in rows:
            sheet.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def office(c):
    cid = company(c, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(c)
    assert c.post('/api/credentials/vault/setup', json={'password': MASTER, 'confirm': MASTER}).status_code == 201
    with SessionLocal() as db:
        db.execute(update(Company).where(Company.id == cid).values(employer_registration='Y1234567890'))
        db.commit()
    return cid


def read(c, data, name='contrasenas.xlsx'):
    r = c.post('/api/credentials/import/read', files={'file': (name, data, 'application/octet-stream')})
    assert r.status_code == 200, r.text
    return r.json()


def preview(c, data, sheet, mapping, decisions=None, name='contrasenas.xlsx'):
    return c.post(
        '/api/credentials/import/preview',
        files={'file': (name, data, 'application/octet-stream')},
        data={'sheet': sheet, 'mapping': json.dumps(mapping), 'decisions': json.dumps(decisions or {})},
    )


def apply(c, data, sheet, mapping, sha, decisions=None, name='contrasenas.xlsx'):
    return c.post(
        '/api/credentials/import/apply',
        files={'file': (name, data, 'application/octet-stream')},
        data={'sheet': sheet, 'mapping': json.dumps(mapping), 'decisions': json.dumps(decisions or {}), 'sha256': sha},
    )


def creds(cid):
    with SessionLocal() as db:
        return list(
            db.execute(
                select(credentials).where(credentials.c.company_id == cid, credentials.c.archived.is_(False))
            ).mappings()
        )


def lines_of(body, rfc):
    entry = next(e for e in body['companies'] if e['rfc'] == rfc)
    return entry, {line['column']: line for line in entry['lines']}


def test_sheet_header_row_columns_and_rules(client):  # noqa: F811
    cid = office(client)
    data = book(
        {
            'Notas': [['Sin datos de contraseñas']],
            'CONTRASEÑAS': [
                ['Relación de contraseñas del despacho'],
                [],
                HEADERS,
                [
                    1,
                    'Servicios Sintéticos',
                    RFC,
                    'Y1234567890',
                    'A',
                    'Ciec-Sint-1',
                    'Fiel-Sint-2',
                    'NA',
                    '-',
                    'Info-1 / Info-2',
                    'Imss-Sint-3',
                    'SIN',
                    'a@b.test / Correo-Sint-4',
                ],
                ['texto suelto sin RFC'],
                [2, 'Empresa Nueva', OTHER, '', 'B', 'Ciec-Otra-5', '', '', '', '', '', '', ''],
            ],
        }
    )
    info = read(client, data)
    assert info['sheet'] == 'CONTRASEÑAS'  # the one with RFC and password columns
    sheet = next(s for s in info['sheets'] if s['name'] == 'CONTRASEÑAS')
    assert sheet['header_row'] == 3
    mapping = sheet['mapping']
    assert dict(zip(HEADERS, mapping, strict=True)) == {
        'NO.': 'ignorar',
        'EMPRESA': 'empresa',
        'RFC': 'rfc',
        'REGISTRO PATRONAL': 'registro_patronal',
        'NIVEL': 'ignorar',
        'Contraseña': 'sat',
        'FIEL EMPRESA': 'fiel_empresa',
        'FIEL REPRE': 'fiel_repre',
        'SELLO DIGITAL': 'csd',
        'INFONAVIT': 'infonavit',
        'Contraseña certificado IMSS': 'imss',
        'SIPARE': 'sipare',
        'CORREO': 'correo',
    }
    first = preview(client, data, 'CONTRASEÑAS', mapping)
    assert first.status_code == 200, first.text
    body = first.json()
    for secret in ('Ciec-Sint-1', 'Fiel-Sint-2', 'Info-1', 'Imss-Sint-3', 'Correo-Sint-4', 'Ciec-Otra-5'):
        assert secret not in first.text
    assert body['ignored_rows'] == 1 and any('texto suelto' in n or 'sin RFC' in n for n in body['notices'])
    entry, lines = lines_of(body, RFC)
    assert lines['Contraseña']['action'] == 'add' and lines['Contraseña']['masked'] == '••••••'
    assert lines['FIEL EMPRESA']['action'] == 'add_incomplete'  # no .cer/.key: «Faltan .cer y .key»
    assert {lines[h]['action'] for h in ('FIEL REPRE', 'SELLO DIGITAL', 'SIPARE')} == {'empty'}  # NA, -, SIN
    assert lines['INFONAVIT']['action'] == 'decide' and lines['INFONAVIT']['decision']['count'] == 2
    assert lines['CORREO']['action'] == 'add'  # address / password
    new, _ = lines_of(body, OTHER)
    assert new['company_id'] is None and {o['id'] for o in new['decision']['options']} == {'create', 'skip'}
    assert body['counts']['decisions'] == 2
    # «Aplicar» waits for every decision.
    assert apply(client, data, 'CONTRASEÑAS', mapping, json.loads(first.text)['sha256']).status_code == 409
    decisions = {lines['INFONAVIT']['id']: 'all', 'rfc:' + OTHER: 'create'}
    ready = preview(client, data, 'CONTRASEÑAS', mapping, decisions).json()
    assert ready['counts']['decisions'] == 0
    done = apply(client, data, 'CONTRASEÑAS', mapping, ready['sha256'], decisions)
    assert done.status_code == 200, done.text
    assert 'borrar el Excel' in done.json()['message'] and done.json()['companies_created'] == 1
    mine = {(r['kind'], r['label']): r for r in creds(cid)}
    assert mine[('SAT_CIEC', 'Acceso')]['username'] == RFC
    assert mine[('IMSS_IDSE', 'Acceso')]['username'] == 'Y1234567890'  # registro patronal as the user
    assert mine[('CORREO', 'Acceso')]['username'] == 'a@b.test'
    assert {k for k in mine if k[0] == 'INFONAVIT'} == {('INFONAVIT', 'Acceso'), ('INFONAVIT', 'Acceso (2)')}
    with SessionLocal() as db:
        incomplete = db.execute(select(certificates).where(certificates.c.company_id == cid)).mappings().first()
        assert incomplete['notes'] == 'Faltan .cer y .key' and incomplete['cert_class'] == 'FIEL_EMPRESA'
        created = db.scalars(select(Company).where(Company.rfc == OTHER)).first()
        assert created and created.name == 'Empresa Nueva'
        log = db.execute(select(audit).where(audit.c.kind == 'IMPORTAR')).mappings().first()
        assert log['metadata']['file'] == 'contrasenas.xlsx' and log['metadata']['counts']['new'] >= 6
        assert 'Ciec' not in str(log)
        assert db.execute(select(import_templates.c.mapping)).scalar() == mapping
    # Same file again: everything «Sin cambios»; a changed value «Actualizar»; NA never deletes.
    again = preview(client, data, 'CONTRASEÑAS', mapping, decisions).json()
    _, lines = lines_of(again, RFC)
    assert lines['Contraseña']['action'] == 'same' and lines['Contraseña']['detail'] == 'igual'
    assert lines['FIEL EMPRESA']['action'] == 'same'
    changed = book(
        {
            'CONTRASEÑAS': [
                HEADERS,
                [1, 'Servicios Sintéticos', RFC, '', '', 'Ciec-Nueva-9', 'NA', '', '', '', '', '', ''],
            ]
        }
    )
    body = preview(client, changed, 'CONTRASEÑAS', default := read(client, changed)['sheets'][0]['mapping']).json()
    _, lines = lines_of(body, RFC)
    assert lines['Contraseña']['action'] == 'update' and lines['Contraseña']['detail'] == 'distinta'
    assert lines['FIEL EMPRESA']['action'] == 'empty'
    apply(client, changed, 'CONTRASEÑAS', default, body['sha256'])
    sat = next(r for r in creds(cid) if r['kind'] == 'SAT_CIEC')
    assert sat['revision'] == 2  # the previous value stays in the history
    assert any(r['kind'] == 'LLAVE' for r in creds(cid))  # NA did not delete the FIEL password


def test_repeated_rfc_notices_and_skip(client):  # noqa: F811
    office(client)
    data = book(
        {
            'Hoja1': [
                HEADERS,
                [1, 'Servicios Sintéticos', RFC, 'X9999999999', '', 'Primera-1', '', '', '', '', '', '', ''],
                [2, 'Otro Nombre SA', RFC, 'X9999999999', '', 'Ultima-2', '', '', '', '', '', '', ''],
                [3, 'Empresa Inexistente', OTHER, '', '', 'Algo-3', '', '', '', '', '', '', ''],
            ]
        }
    )
    mapping = read(client, data)['sheets'][0]['mapping']
    body = preview(client, data, 'Hoja1', mapping, {'rfc:' + OTHER: 'skip'}).json()
    assert any('se repite en las filas 2, 3' in n for n in body['notices'])
    entry, lines = lines_of(body, RFC)
    assert entry['row'] == 3 and entry['repeated_rows'] == [2]
    assert any('registro patronal' in n for n in entry['notices']) and any('nombre' in n for n in entry['notices'])
    skipped, other_lines = lines_of(body, OTHER)
    assert other_lines['Contraseña']['action'] == 'skipped' and body['counts']['decisions'] == 0
    assert apply(client, data, 'Hoja1', mapping, body['sha256'], {'rfc:' + OTHER: 'skip'}).status_code == 200
    with SessionLocal() as db:
        assert not db.scalars(select(Company).where(Company.rfc == OTHER)).first()
        employer = db.scalars(select(Company.employer_registration).where(Company.rfc == RFC)).first()
        assert employer == 'Y1234567890'  # informative notice only


def test_fiel_password_against_the_stored_key(client):  # noqa: F811
    cid = office(client)
    cer, key, _ = pair()
    up = client.post(
        f'/api/credentials/companies/{cid}/certificates/upload',
        files={'cer': ('f.cer', cer, 'application/octet-stream'), 'key': ('f.key', key, 'application/octet-stream')},
        data={'password': 'Llave-Sintetica-1', 'cert_class': 'FIEL_EMPRESA'},
    )
    assert up.status_code == 201, up.text
    for value, action in (('Llave-Sintetica-1', 'same'), ('No-Abre-La-Llave', 'review')):
        data = book({'H': [HEADERS, [1, '', RFC, '', '', '', value, '', '', '', '', '', '']]})
        mapping = read(client, data)['sheets'][0]['mapping']
        body = preview(client, data, 'H', mapping).json()
        entry, lines = lines_of(body, RFC)
        assert lines['FIEL EMPRESA']['action'] == action
        if action == 'review':
            assert any('no abre la llave guardada' in n for n in entry['notices'])
            apply(client, data, 'H', mapping, body['sha256'])
            keys = [r for r in creds(cid) if r['kind'] == 'LLAVE']
            assert len(keys) == 1 and keys[0]['revision'] == 1  # «Revisar» is never applied


def test_csv_remembered_mapping_formats_and_access(client):  # noqa: F811
    office(client)
    text = 'Clave fiscal;rfc;Nombre\nCiec-Latina-ñ;' + RFC + ';Servicios\n'
    data = text.encode('latin-1')
    info = read(client, data, name='otro.csv')
    sheet = info['sheets'][0]
    assert sheet['name'] == 'CSV' and sheet['mapping'] == ['ignorar', 'rfc', 'ignorar']
    mapping = ['sat', 'rfc', 'empresa']  # corrected by the person
    body = preview(client, data, 'CSV', mapping, name='otro.csv').json()
    assert apply(client, data, 'CSV', mapping, body['sha256'], name='otro.csv').status_code == 200
    assert read(client, data, name='otro.csv')['sheets'][0]['mapping'] == mapping  # remembered next time
    assert read_status(client, b'x', 'viejo.xls') == 422
    assert read_status(client, b'x' * (5 * 1024 * 1024 + 1), 'grande.csv') == 422
    bad = preview(client, data, 'CSV', ['sat', 'sat', 'empresa'], name='otro.csv')
    assert bad.status_code == 422  # exactly one RFC column
    client.post('/api/credentials/vault/lock')
    assert read_status(client, data, 'otro.csv') == 423


def read_status(c, data, name):
    return c.post('/api/credentials/import/read', files={'file': (name, data, 'application/octet-stream')}).status_code


def test_template_and_export_with_the_master_password(client):  # noqa: F811
    cid = office(client)
    template = client.get('/api/credentials/import/template')
    assert template.status_code == 200
    sheet = load_workbook(io.BytesIO(template.content)).active
    assert [c.value for c in sheet[1]] == HEADERS[:5] + [
        'CONTRASEÑA',
        'FIEL EMPRESA',
        'FIEL REPRE',
        'SELLO DIGITAL',
        'INFONAVIT',
        'CONTRASEÑA CERTIFICADO IMSS',
        'SIPARE',
        'CORREO',
    ]
    assert sheet.max_row == 1
    client.post(f'/api/credentials/companies/{cid}/secrets', json={'kind': 'SAT_CIEC', 'secret': 'Ciec-Export-1'})
    client.post(
        f'/api/credentials/companies/{cid}/secrets',
        json={'kind': 'CORREO', 'secret': 'Correo-Export-2', 'username': 'a@b.test'},
    )
    wrong = client.post('/api/credentials/export', json={'reason': 'respaldo', 'password': 'otra-maestra-1'})
    assert wrong.status_code == 403
    out = client.post('/api/credentials/export', json={'reason': 'respaldo', 'password': MASTER})
    assert out.status_code == 200 and out.content[:2] == b'PK'
    rows = list(load_workbook(io.BytesIO(out.content)).active.values)
    header, row = list(rows[0]), dict(zip(rows[0], rows[1], strict=True))
    assert header[2] == 'RFC' and row['RFC'] == RFC and row['CONTRASEÑA'] == 'Ciec-Export-1'
    assert row['CORREO'] == 'a@b.test / Correo-Export-2'
    with SessionLocal() as db:
        assert 'EXPORTAR' in set(db.scalars(select(audit.c.kind)))
    # The exported file imports back with no changes.
    info = read(client, out.content, name='contrasenas_contasuite.xlsx')
    body = preview(
        client, out.content, info['sheet'], info['sheets'][0]['mapping'], name='contrasenas_contasuite.xlsx'
    ).json()
    _, lines = lines_of(body, RFC)
    assert lines['CONTRASEÑA']['action'] == 'same' and lines['CORREO']['action'] == 'same'
