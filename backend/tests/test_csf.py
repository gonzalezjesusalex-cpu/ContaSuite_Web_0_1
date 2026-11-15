"""Bloque 1: registering a company from a Constancia de Situación Fiscal (synthetic documents only).

The constancias are generated here: a legal entity with a text layer (reportlab) and an individual scanned and
mixed with other documents (Pillow, no text layer). No file from ARCHIVOS PRUEBA is used.
"""

import io
import random
from datetime import date, timedelta

import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import func, select

from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import login, setup
from test_permissions import account
from app import csf_extract, sat_regimes
from app.database import SessionLocal
from app.models import Audit, Company, CompanyRegime

ISSUED = date.today() - timedelta(days=10)
MONTHS = [
    'ENERO',
    'FEBRERO',
    'MARZO',
    'ABRIL',
    'MAYO',
    'JUNIO',
    'JULIO',
    'AGOSTO',
    'SEPTIEMBRE',
    'OCTUBRE',
    'NOVIEMBRE',
    'DICIEMBRE',
]


def spanish(d):
    return f'{d.day:02d} DE {MONTHS[d.month - 1]} DE {d.year}'


def moral_pdf(rfc='SSB100101AB1', status='ACTIVO', regime='Régimen General de Ley Personas Morales', issued=ISSUED):
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=letter)

    def page(lines):
        y = 740
        for text in lines:
            c.drawString(40, y, text)
            y -= 16
        c.showPage()

    page(
        [
            'CÉDULA DE IDENTIFICACIÓN FISCAL',
            'SERVICIOS SINTÉTICOS DEL BAJÍO',
            'idCIF: 21012345',
            'CONSTANCIA DE SITUACIÓN FISCAL',
            'Lugar y Fecha de Emisión',
            'LEÓN , GUANAJUATO A ' + spanish(issued),
            'Datos de Identificación del Contribuyente:',
            'RFC: ' + rfc,
            'Denominación/Razón Social: SERVICIOS SINTÉTICOS DEL BAJÍO',
            'Régimen Capital: SOCIEDAD ANONIMA DE CAPITAL VARIABLE',
            'Nombre Comercial:',
            'Fecha inicio de operaciones: 01 DE ENERO DE 2010',
            'Estatus en el padrón: ' + status,
            'Datos del domicilio registrado',
            'Código Postal:37000 Tipo de Vialidad: CALLE',
            'Nombre de Vialidad: MADERO Número Exterior: 100',
            'Número Interior: 2 Nombre de la Colonia: CENTRO',
            'Nombre de la Localidad: LEÓN Nombre del Municipio o Demarcación Territorial: LEÓN',
            'Nombre de la Entidad Federativa: GUANAJUATO Entre Calle: JUÁREZ',
            'Y Calle: HIDALGO',
            'Página [1] de [2]',
        ]
    )
    page(
        [
            'Regímenes:',
            'Régimen Fecha Inicio Fecha Fin',
            regime + ' 01/01/2010',
            'Obligaciones:',
            'Descripción de la Obligación Descripción Vencimiento Fecha Inicio Fecha Fin',
            'Declaración anual de ISR del ejercicio Personas morales. A más tardar el 31 de marzo. 01/01/2010',
            'Pago definitivo mensual de IVA. A más tardar el día 17 del mes posterior. 01/01/2010',
            'Entero de retenciones mensuales de ISR por sueldos y salarios. A más tardar el día 17. 01/01/2010',
            'Página [2] de [2]',
        ]
    )
    # A third, unrelated page with text: it must never be read into the result nor attached.
    page(['DOCUMENTO AJENO A LA CONSTANCIA', 'DATO PRIVADO QUE NO DEBE GUARDARSE'])
    c.save()
    return out.getvalue()


def text_page(lines, title=None):
    img = Image.new('RGB', (1700, 2200), 'white')
    d = ImageDraw.Draw(img)
    y = 120
    if title:
        d.text((150, y), title, fill='black', font=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 44))
        y += 110
    for text in lines:
        d.text((150, y), text, fill='black', font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 32))
        y += 62
    return img


def scanned(img, seed):
    rnd = random.Random(seed)
    img = img.convert('L').rotate(rnd.uniform(-2.5, 2.5), expand=True, fillcolor=235)
    img = Image.blend(img, Image.effect_noise(img.size, 28), 0.12).filter(ImageFilter.GaussianBlur(0.7))
    return img.resize((img.width * 3 // 4, img.height * 3 // 4))


def physical_scan():
    csf = text_page(
        [
            'CÉDULA DE IDENTIFICACIÓN FISCAL',
            'idCIF: 19080123456',
            'RFC: SINT850101AB3',
            'CURP: SINT850101HJCRRN09',
            'Nombre (s): JUAN CARLOS',
            'Primer Apellido: PÉREZ',
            'Segundo Apellido: NÚÑEZ',
            'Fecha inicio de operaciones: 01 DE MARZO DE 2010',
            'Estatus en el padrón: ACTIVO',
            'Código Postal: 44100',
            'Nombre de la Entidad Federativa: JALISCO',
            'Regímenes:',
            'Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios 01/03/2010',
        ],
        title='CONSTANCIA DE SITUACIÓN FISCAL',
    )
    other = text_page(['DOCUMENTO DE IDENTIFICACIÓN FICTICIO', 'CLAVE: XXXX000000'])
    pages = [scanned(p, i) for i, p in enumerate([other, csf, other])]
    out = io.BytesIO()
    pages[0].save(out, format='PDF', save_all=True, append_images=pages[1:], resolution=150)
    return out.getvalue()


def upload(c, data, company_id=None, path='/api/companies/csf/analyze'):
    return c.post(path, files={'file': ('csf.pdf', data, 'application/pdf')}, data={'company_id': company_id or ''})


# ------------------------------------------------------------------ extraction


def test_text_layer_constancia_fills_the_form_without_the_other_pages():
    result = csf_extract.analyze(moral_pdf())
    f = result['fields']
    assert result['source'] == 'text' and result['pages'] == [1, 2] and result['page_count'] == 3
    assert (f['person_type'], f['rfc'], f['idcif']) == ('Moral', 'SSB100101AB1', '21012345')
    assert f['name'] == 'SERVICIOS SINTÉTICOS DEL BAJÍO'
    assert (f['tax_postal_code'], f['tax_street'], f['tax_state']) == ('37000', 'MADERO', 'GUANAJUATO')
    assert f['tax_between_streets'] == 'JUÁREZ y HIDALGO' and f['padron_status'] == 'ACTIVO'
    assert f['operations_start'] == date(2010, 1, 1) and f['csf_issued_on'] == ISSUED
    assert f['regime'] == '601 - General de Ley Personas Morales' and f['regimes'][0]['code'] == '601'
    assert result['low_confidence'] == [] and result['warnings'] == []
    assert len(result['obligations']) == 3
    assert 'DATO PRIVADO' not in repr(result)


@pytest.mark.skipif(not csf_extract.ocr_available(), reason='OCR local no instalado')
def test_scanned_individual_constancia_mixed_with_other_documents_uses_local_ocr():
    result = csf_extract.analyze(physical_scan())
    f = result['fields']
    assert result['source'] == 'ocr' and result['pages'] == [2] and result['page_count'] == 3
    assert (f['person_type'], f['rfc'], f['curp'], f['idcif']) == (
        'Física',
        'SINT850101AB3',
        'SINT850101HJCRRN09',
        '19080123456',
    )
    assert f['name'] == 'JUAN CARLOS PÉREZ NÚÑEZ' and f['regime'].startswith('605 ')
    # Identifiers read by OCR always need the user's review.
    assert {'rfc', 'curp', 'idcif'} <= set(result['low_confidence'])
    assert 'FICTICIO' not in repr(result) and 'XXXX000000' not in repr(result)


def two_page_scan():
    """Like real scans: the title is repeated on every page, regimes are on page 2, and the issue date is split by
    the other column («…, A 15 DE» / «NOMBRE, DENOMINACIÓN O RAZÓN» / «SOCIAL» / «NOVIEMBRE DE 2025»)."""
    month = MONTHS[ISSUED.month - 1]
    first = text_page(
        [
            'CÉDULA DE IDENTIFICACIÓN FISCAL',
            'idCIF: 19080123456',
            'LUGAR Y FECHA DE EMISIÓN',
            'ZAPOPAN, JALISCO A ' + str(ISSUED.day) + ' DE',
            'NOMBRE, DENOMINACIÓN O RAZÓN',
            'SOCIAL',
            month + ' DE ' + str(ISSUED.year),
            'RFC: SINT850101AB3',
            'CURP: SINT850101HJCRRN09',
            'Nombre (s): JUAN CARLOS',
            'Primer Apellido: PÉREZ',
            'Estatus en el padrón: ACTIVO',
            'Código Postal: 44100',
            'Página [1] de [2]',
        ],
        title='CONSTANCIA DE SITUACIÓN FISCAL',
    )
    second = text_page(
        [
            'Regímenes:',
            'Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios 01/03/2010',
            'Cadena Original Sello: ||sintetica||',
            'Página [2] de [2]',
        ],
        title='CONSTANCIA DE SITUACIÓN FISCAL',
    )
    pages = [scanned(p, i + 7) for i, p in enumerate([first, second])]
    out = io.BytesIO()
    pages[0].save(out, format='PDF', save_all=True, append_images=pages[1:], resolution=150)
    return out.getvalue()


@pytest.mark.skipif(not csf_extract.ocr_available(), reason='OCR local no instalado')
def test_scan_with_the_title_on_every_page_reads_all_its_pages_and_the_split_issue_date():
    result = csf_extract.analyze(two_page_scan())
    f = result['fields']
    assert result['source'] == 'ocr' and result['pages'] == [1, 2]
    assert 'regime' in f and 'csf_issued_on' in f, (sorted(f), result['warnings'])
    assert f['regime'].startswith('605 ') and f['csf_issued_on'] == ISSUED


def test_issue_date_split_by_the_other_column_in_text():
    text = 'Lugar y Fecha de Emisión\nZAPOPAN, JALISCO A 5 DE\nNOMBRE, DENOMINACIÓN O RAZÓN\nSOCIAL\nMARZO DE 2026\n'
    assert csf_extract.issued_near_label(text) == date(2026, 3, 5)
    assert csf_extract.issued_near_label('Lugar y Fecha de Emisión\nsin fecha legible') is None


def test_notices_and_errors_never_guess_or_leak_data():
    bad_regime = csf_extract.analyze(
        moral_pdf(status='SUSPENDIDO', regime='Régimen Inventado de Prueba', issued=date.today() - timedelta(days=200))
    )
    warnings = ' '.join(bad_regime['warnings'])
    assert 'ACTIVO' in warnings and '3 meses' in warnings and 'manualmente' in warnings
    assert 'regime' not in bad_regime['fields'] and bad_regime['unmatched_regimes'] == ['Régimen Inventado de Prueba']
    # Not a constancia, not a PDF, too large: plain messages without document data.
    other = io.BytesIO()
    c = canvas.Canvas(other)
    c.drawString(40, 700, 'FACTURA SINTETICA RFC SSB100101AB1')
    c.save()
    for data, fragment in [
        (other.getvalue(), 'no contiene'),
        (b'not a pdf', 'PDF'),
        (b'%PDF' + b'0' * csf_extract.MAX_BYTES, '15 MB'),
    ]:
        with pytest.raises(csf_extract.CsfError) as error:
            csf_extract.analyze(data)
        assert fragment in str(error.value) and 'SSB100101AB1' not in str(error.value)


def test_regime_catalog_matches_only_exact_wordings():
    assert len(sat_regimes.REGIMES) == 19
    assert sat_regimes.match('Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios') == '605'
    assert sat_regimes.match('RÉGIMEN SIMPLIFICADO DE CONFIANZA') == '626'
    assert sat_regimes.match('Régimen parecido de confianza') is None


def test_obligation_suggestions_follow_explicit_rules():
    obligations = csf_extract.analyze(moral_pdf())['obligations']
    rows = [('a', 'ISR'), ('b', 'IVA'), ('c', 'Retenciones'), ('d', 'DIOT')]
    suggested = {s['label']: s for s in csf_extract.suggest_obligations(obligations, rows, {'b': (True, 3)})}
    assert set(suggested) == {'ISR', 'Retenciones'}  # IVA already active; withholding is not the own ISR
    assert len(suggested['ISR']['sources']) == 1


# ------------------------------------------------------------------ API


def test_analyze_saves_nothing_and_reports_an_existing_rfc_without_merging(client):  # noqa: F811
    existing = company(client, name='Ya registrada', rfc='SSB100101AB1').json()['id']
    setup(client)
    before = {name: SessionLocal().scalar(select(func.count()).select_from(m)) for name, m in [('c', Company)]}
    result = upload(client, moral_pdf())
    assert result.status_code == 200, result.text
    body = result.json()
    assert body['existing_company'] == {'id': existing, 'name': 'Ya registrada'}
    assert 'No se fusionará' in body['warnings'][0]
    assert {s['label'] for s in body['suggested_obligations']} >= {'ISR', 'IVA', 'Retenciones'}
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Company)) == before['c']
    # Updating a company only accepts its own constancia.
    other = company(client, name='Otra', rfc='OTR010101AB1').json()['id']
    assert upload(client, moral_pdf(), other).status_code == 422
    assert upload(client, b'%PDF-1.4 roto').status_code == 422


def test_who_may_read_and_attach_and_only_the_constancia_pages_are_stored(client):  # noqa: F811
    cid = company(client, name='Servicios Sintéticos', rfc='SSB100101AB1').json()['id']
    other = company(client, name='Otra', rfc='OTR010101AB1').json()['id']
    setup(client)
    account(client, 'aux', 'auxiliar', [(cid, 'read')], actions=[])
    login(client, 'aux')
    assert upload(client, moral_pdf()).status_code == 403  # cannot register companies
    assert upload(client, moral_pdf(), cid).status_code == 403  # cannot edit this one
    assert upload(client, moral_pdf(), path='/api/companies/' + cid + '/csf/attach').status_code == 403
    login(client, 'admin')
    assert upload(client, moral_pdf(), path='/api/companies/' + other + '/csf/attach').status_code == 422
    attached = upload(client, moral_pdf(), path='/api/companies/' + cid + '/csf/attach')
    assert attached.status_code == 201, attached.text
    doc = attached.json()
    stored = client.get('/api/storage/documents/' + doc['id'] + '/content')
    assert stored.status_code == 200
    reader = PdfReader(io.BytesIO(stored.content))
    assert len(reader.pages) == 2  # pages 1-2 of the constancia; the unrelated page 3 is not stored
    assert 'DATO PRIVADO' not in ''.join(p.extract_text() or '' for p in reader.pages)
    with SessionLocal() as db:
        assert db.get(Company, cid).csf_issued_on == ISSUED
        assert db.scalar(select(Audit).where(Audit.action == 'Constancia de Situación Fiscal adjuntada'))


def test_company_fields_validation_regimes_and_history(client):  # noqa: F811
    setup(client)
    base = {'name': 'Juan Carlos Pérez Núñez', 'rfc': 'SINT850101AB3', 'person_type': 'Física'}
    for extra in [
        {'idcif': '1234567'},  # 7 digits
        {'idcif': '123456789012'},  # 12 digits
        {'curp': 'NOESUNACURP'},
        {'curp': 'OTRO850101HJCRRN09'},  # first 10 characters differ from the RFC
        {'tax_postal_code': '4410'},
        {'regimes': [{'code': '6O5', 'label': 'x'}]},
    ]:
        assert client.post('/api/companies', json={**base, **extra}).status_code == 422, extra
    created = client.post(
        '/api/companies',
        json={
            **base,
            'idcif': '19080123',
            'curp': 'SINT850101HJCRRN09',
            'regime': sat_regimes.label('605'),
            'operations_start': '2010-03-01',
            'regimes': [
                {'code': '605', 'label': sat_regimes.label('605'), 'start_date': '2010-03-01'},
                {'code': '612', 'label': sat_regimes.label('612')},
            ],
        },
    )
    assert created.status_code == 201, created.text
    cid = created.json()['id']
    state = next(c for c in client.get('/api/state').json()['companies'] if c['id'] == cid)
    assert [r['code'] for r in state['regimes']] == ['605', '612'] and state['idcif'] == '19080123'
    keep = {k: state[k] for k in ('name', 'rfc', 'person_type', 'regime', 'idcif', 'curp')}
    edited = client.put(
        '/api/companies/' + cid,
        json={**keep, 'tax_postal_code': '44100', 'regimes': [{'code': '612', 'label': sat_regimes.label('612')}]},
    )
    assert edited.status_code == 200, edited.text
    with SessionLocal() as db:
        assert [r.code for r in db.scalars(select(CompanyRegime).where(CompanyRegime.company_id == cid))] == ['612']
        change = db.scalar(
            select(Audit).where(Audit.company_id == cid, Audit.action == 'Datos de empresa actualizados')
        )
    assert change.changes['tax_postal_code'] == {'before': None, 'after': '44100'}
    assert change.changes['regimes']['after'] == [sat_regimes.label('612')]
    # Omitting `regimes` keeps them; other edits do not touch the list.
    assert client.put('/api/companies/' + cid, json={**keep, 'tax_postal_code': '44100'}).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CompanyRegime).where(CompanyRegime.company_id == cid)) == 1
    assert client.get('/api/sat/regimes').json()[0] == {
        'code': '601',
        'label': '601 - General de Ley Personas Morales',
        'fisica': False,
        'moral': True,
    }
