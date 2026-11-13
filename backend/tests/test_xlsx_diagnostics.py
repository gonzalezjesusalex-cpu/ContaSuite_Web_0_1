import io, json
from zipfile import ZipFile, ZIP_DEFLATED
from openpyxl import Workbook
import pytest
from app.company_xlsx import read_xlsx, InvalidWorkbook
from test_company_import import imported, workbook
from test_storage_core import core
from test_api import client


def book(headers=('Empresa', 'RFC'), value='Synthetic company', link=None, column=None):
    b = Workbook()
    w = b.active
    w.append(headers)
    w.append([value, 'AAA010101AA1'])
    if link:
        w['A2'].hyperlink = link
    if column:
        w.cell(1, column, 'far outside allowed columns')
    stream = io.BytesIO()
    b.save(stream)
    b.close()
    return stream.getvalue()


def test_web_hyperlinks_are_passive_and_never_fetched():
    result = read_xlsx(book(link='https://example.invalid/never-fetch'), 'fiscal_metadata')
    assert result['rows'][0]['name'] == 'Synthetic company'
    assert 'never-fetch' not in json.dumps(result)


@pytest.mark.parametrize('link', ['file:///C:/private.xlsx', '\\\\server\\private.xlsx'])
def test_file_and_network_hyperlinks_are_rejected(link):
    with pytest.raises(InvalidWorkbook) as exc:
        read_xlsx(book(link=link), 'fiscal_metadata')
    assert exc.value.code == 'external_relationship' and link not in str(exc.value)


def test_dimensions_and_headers_report_precise_safe_reasons():
    with pytest.raises(InvalidWorkbook) as exc:
        read_xlsx(book(column=101), 'fiscal_metadata')
    assert exc.value.code == 'column_limit'
    with pytest.raises(InvalidWorkbook) as exc:
        read_xlsx(book(headers=('Unrecognized', 'SYNTHETIC-SECRET')), 'fiscal_metadata')
    assert exc.value.code == 'missing_headers' and 'SYNTHETIC-SECRET' not in str(exc.value)


def test_missing_default_style_is_not_treated_as_corruption():
    stream = io.BytesIO()
    with ZipFile(io.BytesIO(book())) as source, ZipFile(stream, 'w', ZIP_DEFLATED) as output:
        for name in source.namelist():
            data = source.read(name)
            if name == 'xl/styles.xml':
                import re

                data = re.sub(rb'<cellStyles[^>]*>.*?</cellStyles>', b'<cellStyles count="0"/>', data)
            output.writestr(name, data)
    result = read_xlsx(stream.getvalue(), 'fiscal_metadata')
    assert len(result['rows']) == 1 and result['presentation_warnings_omitted'] == 1


def test_authorized_real_preview_never_applies_company_changes(imported):
    c, factory, _ = imported
    endpoint = '/api/company-imports/preview/xlsx?source=fiscal_metadata'
    assert c.post(endpoint, content=workbook()).status_code == 423
    response = c.post(endpoint + '&authorized_read=true', content=workbook())
    assert response.status_code == 200, response.text
    assert response.json()['confirmation_enabled'] is False
    assert 'SYNTHETIC-SECRET' not in response.text
    ident = response.json()['id']
    assert c.post('/api/company-imports/' + ident + '/confirm', json={'confirmed': True}).status_code == 423
    failure = c.post(endpoint + '&authorized_read=true', content=book(column=101))
    assert failure.status_code == 422 and '100 columnas' in failure.json()['detail']
