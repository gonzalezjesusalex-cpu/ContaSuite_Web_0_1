"""«Importar > Vista previa» of the Excel «Control de obligaciones»: admin only, in memory, no fiscal write (3A.6)."""

from test_accounts import login
from test_agent_links import office  # noqa: F401
from test_fiscal_xlsx import workbook_bytes
from test_virtual_copy import client  # noqa: F401

URL = '/api/fiscal-control/import/preview'
RAW = {'Content-Type': 'application/octet-stream'}


def test_preview_is_admin_only_and_needs_explicit_authorization(office):  # noqa: F811
    c, _, _ = office
    assert c.post(URL, content=workbook_bytes(), headers=RAW).status_code == 423
    assert c.post(URL + '?authorized_read=true', content=b'basura', headers=RAW).status_code == 422
    login(c, 'ana')
    assert c.post(URL + '?authorized_read=true', content=workbook_bytes(), headers=RAW).status_code == 403
    assert c.get('/api/fiscal-control/import/equivalences').status_code == 403


def test_preview_reports_sheets_without_writing_any_fiscal_record(office):  # noqa: F811
    c, companies, _ = office
    reply = c.post(URL + '?authorized_read=true', content=workbook_bytes(), headers=RAW)
    assert reply.status_code == 200, reply.text
    data = reply.json()
    assert data['applied'] is False
    assert [s['name'] for s in data['sheets']] == ['OCT 26', 'ENE 22']
    assert data['ignored_sheets'] == [{'name': 'OCT20', 'reason': 'hidden'}]
    oct26 = data['sheets'][0]
    assert oct26['rows'] == 2 and oct26['confirmed'] == 0 and oct26['unmatched'] == 2
    assert all(row['cells'] == [] for row in oct26['detail'])  # no confirmed equivalence: nothing enters the proposal
    assert {n['excel_name'] for n in data['names_to_confirm']} == {'ALFA SERVICIOS SA', 'BETA COMERCIAL SA'}
    assert data['equivalences_available'] is False
    from sqlalchemy import func, select

    from app.database import SessionLocal
    from app.fiscal_control import import_rows, imports, records

    with SessionLocal() as db:
        for table in (records, imports, import_rows):
            assert db.scalar(select(func.count()).select_from(table)) == 0
    # Equivalences need their explicit migration: confirming is refused, nothing is stored.
    refused = c.put(
        '/api/fiscal-control/import/equivalences',
        json={'excel_name': 'ALFA SERVICIOS SA', 'company_id': companies['a']},
    )
    assert refused.status_code == 503
    assert c.get('/api/fiscal-control/import/equivalences').json() == {'available': False, 'items': []}
