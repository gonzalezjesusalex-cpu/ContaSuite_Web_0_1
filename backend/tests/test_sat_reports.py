"""Excel reports of the SAT saved into the expediente as «Reportes del SAT» (.xlsx only, from CFDI)."""

import io
import zipfile
from functools import cache

from openpyxl import Workbook

from test_api import A, client, company  # noqa: F401
from test_organizador import RFC
from test_organizador_api import run, xml
from test_organizador_review import U1

REPORT = f'EMITIDOS-{RFC}-202604.xlsx'


@cache
def workbook(value='1'):
    # Cached: openpyxl stamps the creation time, and the same report must have the same bytes (same SHA-256).
    book = Workbook()
    book.active.append(['UUID', 'Total', value])
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def package(extra=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('xl/workbook.xml', '<workbook/>')
        for name in extra or []:
            z.writestr(name, b'x')
    return stream.getvalue()


def upload(client, data, name=REPORT, document_type='sat_report', company_id=''):
    return client.post(
        '/api/storage/documents',
        headers=A,
        files={'file': (name, data, 'application/octet-stream')},
        data={'company_id': company_id, 'document_type': document_type, 'period': '2026-04'},
    )


def test_xlsx_is_admitted_only_as_a_sat_report_and_only_as_a_plain_workbook(client):  # noqa: F811
    c = company(client).json()
    assert upload(client, workbook(), document_type='other', company_id=c['id']).status_code >= 400
    assert upload(client, workbook(), document_type='cfdi', company_id=c['id']).status_code >= 400
    assert upload(client, b'not a workbook', company_id=c['id']).status_code >= 400
    assert upload(client, package(['xl/vbaProject.bin']), company_id=c['id']).status_code >= 400
    assert upload(client, package(['xl/externalLinks/externalLink1.xml']), company_id=c['id']).status_code >= 400
    assert upload(client, package(), name='macro.xlsm', company_id=c['id']).status_code >= 400
    assert upload(client, workbook(), name='viejo.xls', company_id=c['id']).status_code >= 400
    ok = upload(client, workbook(), company_id=c['id'])
    assert ok.status_code == 201, ok.text
    assert ok.json()['document_type'] == 'sat_report'
    # Download is verified and returns the exact bytes; there is no preview for spreadsheets.
    ident = ok.json()['id']
    assert client.get(f'/api/storage/documents/{ident}/content', headers=A).content == workbook()
    assert (
        client.get(f'/api/storage/documents/{ident}/content', headers=A, params={'preview': 'true'}).status_code == 415
    )


def entries():
    folder = f'Base/Emitidos/{RFC}/2026-04/'
    return {folder + 'ok.xml': xml(U1), 'Base/Reportes/' + REPORT: workbook()}


def test_cfdi_saves_the_excel_report_and_keeps_it_out_of_the_folder_write(client):  # noqa: F811
    c = company(client).json()
    base = run(client, entries(), c['id'])
    detail = client.get(base, headers=A).json()
    report = next(r for r in detail['review'].values() if r['name'] == REPORT)
    assert report['pair'] == 'no_aplica' and report['ext'] == '.xlsx'
    preview = client.get(base + '/save-preview', headers=A).json()
    assert preview['counts'] == {'nuevo': 2, 'ya_registrado': 0, 'revision': 0, 'bloqueado': 0}

    saved = client.post(base + '/save', headers=A, json={}).json()
    assert {i['name']: i['state'] for i in saved['items']} == {'ok.xml': 'saved', REPORT: 'saved'}
    docs = client.get('/api/storage/documents', headers=A, params={'company_id': c['id']}).json()['items']
    assert {(d['name'], d['document_type'], d['period']) for d in docs} == {
        ('ok.xml', 'cfdi', '2026-04'),
        (REPORT, 'sat_report', '2026-04'),
    }
    queue = client.get('/api/organizador/companies/' + c['id'] + '/review', headers=A).json()
    assert [(p['xml'], p['pdf'], p['reports']) for p in queue['periods']] == [(1, 0, 1)]

    # The same report again is already registered (same SHA-256 linked to the company); nothing is duplicated.
    again = run(client, entries(), c['id'])
    assert client.get(again + '/save-preview', headers=A).json()['counts']['ya_registrado'] == 2
    client.post(again + '/save', headers=A, json={})
    assert len(client.get('/api/storage/documents', headers=A, params={'company_id': c['id']}).json()['items']) == 2

    # A different report with the same name becomes a new version; it never overwrites the previous bytes.
    changed = dict(entries(), **{'Base/Reportes/' + REPORT: workbook('2')})
    third = run(client, changed, c['id'])
    assert client.get(third + '/save-preview', headers=A).json()['counts']['nuevo'] == 1
    client.post(third + '/save', headers=A, json={})
    docs = client.get('/api/storage/documents', headers=A, params={'company_id': c['id']}).json()['items']
    assert len(docs) == 2
