"""Plan v1.1 (docs/PLAN_V1_1_SEGUIMIENTO.md): obligations checklist, document traffic light, CFDI calendar and
password manager. Synthetic documents only: every PDF, XML and Excel is generated here; no real document is used.
"""

import base64
import io
import json
import os
from datetime import date, timedelta

import pytest
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import select

from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import PASSWORD, add_user, login, setup
from app import compliance_extract, csf_extract
from app import obligation_catalog as oc
from app.credential_crypto import VaultCipher, strength
from app.credential_models import audit, credentials
from app.database import SessionLocal
from app.fiscal_control import history, records

RFC = 'SSB100101AB1'
TODAY = date.today()


def pdf(pages, producer='ReportLab'):
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=letter)
    c._doc.info.producer = producer
    for lines in pages:
        y = 750
        for item in lines:
            if isinstance(item, tuple):  # table row: (x, text) cells
                for x, text in item:
                    c.drawString(x, y, text)
            else:
                c.drawString(40, y, item)
            y -= 15
        c.showPage()
    c.save()
    return out.getvalue()


def spanish(d):
    months = [
        'enero',
        'febrero',
        'marzo',
        'abril',
        'mayo',
        'junio',
        'julio',
        'agosto',
        'septiembre',
        'octubre',
        'noviembre',
        'diciembre',
    ]
    return f'{d.day} de {months[d.month - 1]} de {d.year}'


HEADER = (
    (40, 'Descripción de la Obligación'),
    (300, 'Descripción Vencimiento'),
    (470, 'Fecha Inicio'),
    (540, 'Fecha Fin'),
)


def oracle_csf(rfc=RFC, issued=TODAY):
    """Persona moral, three pages, table with column positions (Oracle XML Publisher style)."""
    head = [
        'CÉDULA DE IDENTIFICACIÓN FISCAL',
        'idCIF: 21012345',
        'CONSTANCIA DE SITUACIÓN FISCAL',
        'Lugar y Fecha de Emisión',
        'LEÓN , GUANAJUATO A ' + spanish(issued).upper(),
    ]
    return pdf(
        [
            head
            + [
                'Datos de Identificación del Contribuyente:',
                'RFC: ' + rfc,
                'Denominación/Razón Social: SERVICIOS SINTÉTICOS',
                'Estatus en el padrón: ACTIVO',
                'Página [1] de [3]',
            ],
            [
                'Página [2] de [3]',
                'Regímenes:',
                'Régimen Fecha Inicio Fecha Fin',
                'Régimen General de Ley Personas Morales 01/01/2010',
            ],
            [
                'Página [3] de [3]',
                'Obligaciones:',
                HEADER,
                ((40, 'Pago definitivo mensual de IVA.'), (300, 'A más tardar el día 17 del mes'), (470, '01/01/2010')),
                ((300, 'inmediato posterior al periodo que corresponda.'),),
                (
                    (40, 'Declaración de proveedores de IVA'),
                    (300, 'A más tardar el último día del mes'),
                    (470, '01/01/2010'),
                ),
                (
                    (40, 'Pago provisional trimestral de ISR de personas'),
                    (300, 'A más tardar el día 17'),
                    (470, '01/01/2011'),
                    (540, '31/03/2011'),
                ),
                ((40, 'morales por inicio de segundo ejercicio. Régimen General.'),),
                (
                    (40, 'Obligación inventada de prueba sin catálogo'),
                    (300, 'A más tardar el día 10'),
                    (470, '01/01/2012'),
                ),
                'Cadena Original Sello: ||'
                + issued.strftime('%Y/%m/%d')
                + ' 10:11:12|'
                + rfc
                + '|CONSTANCIA DE SITUACIÓN FISCAL|2000||',
            ],
        ],
        'Oracle XML Publisher 5.6.2',
    )


def cairo_csf(header=True):
    """Persona física RESICO, two pages, another generator; with or without the column header."""
    rows = [
        (
            (40, 'Pago provisional mensual de ISR. Régimen Simplificado de'),
            (300, 'A más tardar el día 17'),
            (470, '01/01/2022'),
        ),
        ((40, 'Confianza.'),),
        (
            (40, 'Ajuste anual de ISR correspondiente a la declaración anual.'),
            (300, 'A más tardar el día 30 del mes de abril'),
            (470, '01/01/2022'),
        ),
        ((40, 'Régimen Simplificado de Confianza.'), (300, 'del ejercicio siguiente.')),
    ]
    return pdf(
        [
            [
                'CONSTANCIA DE SITUACIÓN FISCAL',
                'RFC: GOMJ800101AB2',
                'CURP: GOMJ800101HGTRRN09',
                'Regímenes:',
                'Régimen Simplificado de Confianza 01/01/2022',
                'Página [1] de [2]',
            ],
            ['Página [2] de [2]', 'Obligaciones:']
            + ([HEADER] if header else [])
            + rows
            + ['Cadena Original Sello: ||2026/11/20 10:11:12|GOMJ800101AB2|CONSTANCIA DE SITUACIÓN FISCAL|2000||'],
        ],
        'cairo 1.16.0',
    )


def infonavit_pdf(rfc=RFC, issued=TODAY, workers=9, debt=False):
    result = (
        'No se encuentra al corriente; la constancia que se emite es con adeudo.'
        if debt
        else 'Sí se encuentra al corriente en el cumplimiento; la constancia que se emite es sin adeudo.'
    )
    return pdf(
        [
            [
                'Instituto del Fondo Nacional de la Vivienda para los Trabajadores',
                'CONSTANCIA DE SITUACIÓN FISCAL EN MATERIA OBLIGACIONES FISCALES RELATIVA',
                'A LAS APORTACIONES PATRONALES Y ENTERO DE DESCUENTOS',
                'León, Guanajuato a ' + spanish(issued),
                'Folio: 123456/' + str(issued.year),
                'RFC: ' + rfc,
                'Razón social: SERVICIOS SINTÉTICOS',
                result,
                f'cuenta con {workers} trabajador(es) activo(s) ante el Infonavit al 4to. Bimestre de {issued.year}',
                f'Cadena original: 123456/{issued.year} | {rfc}|',
            ]
        ],
        'SAP NetWeaver',
    )


def sat_opinion_pdf(rfc=RFC, issued=TODAY, sense='P', folio='26NA1234567', tamper=False):
    visible = 'POSITIVO' if sense == 'P' else 'NEGATIVO'
    lines = [
        'SERVICIO DE ADMINISTRACIÓN TRIBUTARIA',
        'Opinión del cumplimiento de obligaciones fiscales',
        'SERVICIOS SINTÉTICOS',
        'Sentido: ' + ('NEGATIVO' if tamper else visible),
        'RFC: ' + rfc,
        'Folio: ' + folio,
        'Fecha y hora de emisión: ' + spanish(issued) + ' a las 22:41 horas',
    ]
    if sense == 'N':
        lines += [
            'Cumplimiento de obligaciones',
            'Declaración anual de ISR del ejercicio Personas morales.',
            str(issued.year - 1),
        ]
    lines += ['Cadena original:', f'||{rfc}|{folio}|{issued.strftime("%d-%m-%Y")}|{sense}||00001000000512345678||']
    return pdf([lines], 'Apache FOP')


def imss_pdf(rfc=RFC, issued=TODAY, opinion='POSITIVA', workers=3):
    months = spanish(issued).replace(' de ' + str(issued.year), ' ' + str(issued.year))  # «de» missing before year
    return pdf(
        [
            [
                'INSTITUTO MEXICANO DEL SEGURO SOCIAL',
                'Opinión de cumplimiento de obligaciones en materia de seguridad social',
                'Folio: 12345678901234567890123',
                'Clave de RFC: ' + rfc,
                f'se emite opinión {opinion.capitalize()}',
                f'Usted tiene registrado(s) {workers} trabajador(es) activo(s)',
                'Cadena original:',
                f'Invocante:IMSS|Tramite:32D|Fecha:{months}|Folio:12345678901234567890123|RFC:{rfc}|',
                f'Nombre o Razon Social:SERVICIOS SINTETICOS|CURP:|Opinion:{opinion}|',
                f'FechaInicioVigencia:{months}|FechaFinVigencia:{months}|',
            ]
        ],
        'JasperReports CartaNoAdeudo',
    )


# ------------------------------------------------------------------ CSF reader (Bloque 1 + Cambio 2)


def test_csf_reader_rejects_the_infonavit_constancia():
    with pytest.raises(csf_extract.CsfError) as error:
        csf_extract.analyze(infonavit_pdf())
    assert 'Infonavit' in str(error.value) and RFC not in str(error.value)


@pytest.mark.parametrize('maker', [oracle_csf, lambda: cairo_csf(True), lambda: cairo_csf(False)])
def test_csf_obligations_do_not_depend_on_the_pdf_generator(maker):
    result = csf_extract.analyze(maker())
    names = [o['description'] for o in result['obligations']]
    assert result['fields']['csf_issued_on']
    if 'GOMJ' in result['fields']['rfc']:
        assert names == [
            'Pago provisional mensual de ISR. Régimen Simplificado de Confianza.',
            'Ajuste anual de ISR correspondiente a la declaración anual. Régimen Simplificado de Confianza.',
        ]
        assert oc.parse_due_rule(result['obligations'][1]['due_text']) == {
            'kind': 'fixed_next_year',
            'month': 4,
            'day': 30,
        }
    else:
        assert names[0] == 'Pago definitivo mensual de IVA.'
        trimestral = result['obligations'][2]
        assert trimestral['description'].endswith('segundo ejercicio. Régimen General.')
        assert (trimestral['start_date'], trimestral['end_date']) == (date(2011, 1, 1), date(2011, 3, 31))


def test_csf_proposals_match_the_catalog_exactly_and_list_the_rest():
    entries = [
        {'id': k, 'official_name': n, 'aliases': oc.ALIASES.get(k), 'short_name': s, 'group_name': g, 'cadence': cad}
        for k, n, s, g, cad, *_ in oc.INITIAL
    ]
    proposals, unmatched = csf_extract.propose_csf_obligations(
        csf_extract.analyze(oracle_csf())['obligations'], entries
    )
    assert {p['obligation_id'] for p in proposals} == {
        'v11-iva-mensual',
        'v11-iva-proveedores',
        'v11-isr-pm-trimestral',
    }
    assert [u['description'] for u in unmatched] == ['Obligación inventada de prueba sin catálogo']
    resico = csf_extract.propose_csf_obligations(csf_extract.analyze(cairo_csf())['obligations'], entries)[0]
    # The RESICO wording is never confused with the general one.
    assert {p['obligation_id'] for p in resico} == {'v11-isr-resico-pf', 'v11-ajuste-resico'}


def test_due_rules_and_periods():
    assert oc.normalize('Pago definitivo mensual de IVA.') == oc.normalize('PAGO DEFINITIVO  mensual de iva')
    assert oc.due_date({'kind': 'day_next_month', 'day': 17}, date(2026, 12, 31)) == date(2027, 1, 17)
    assert oc.due_date({'kind': 'last_day_next_month'}, date(2026, 1, 31)) == date(2026, 2, 28)
    assert oc.due_date({'kind': 'months_after_year_end', 'months': 3}, date(2026, 12, 31)) == date(2027, 3, 31)
    assert oc.parse_due_rule('Dentro de los tres meses siguientes al cierre del ejercicio.') == {
        'kind': 'months_after_year_end',
        'months': 3,
    }
    assert oc.period_key('bimonthly', 2026, 5) == '2026-B3' and oc.shown_in('bimonthly', 6)
    assert not oc.shown_in('quarterly', 5) and oc.shown_in('annual', 12) and not oc.shown_in('annual', 11)
    assert oc.active_in(date(2011, 1, 1), date(2011, 3, 31), date(2011, 4, 1), date(2011, 4, 30)) is False


# ------------------------------------------------------------------ checklist API (Cambio 2)


def test_checklist_assign_mark_history_overdue_and_export(client):  # noqa: F811
    cid = company(client, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(client)
    analyzed = client.post(
        '/api/companies/csf/analyze',
        files={'file': ('csf.pdf', oracle_csf(), 'application/pdf')},
        data={'company_id': cid},
    )
    assert analyzed.status_code == 200, analyzed.text
    body = analyzed.json()
    assert len(body['csf_obligations']) == 3 and len(body['unmatched_obligations']) == 1
    for o in body['csf_obligations']:
        r = client.put(
            '/api/fiscal-control/applicability',
            json={
                'company_id': cid,
                'obligation_id': o['obligation_id'],
                'applicable': True,
                'revision': 0,
                'start_date': o['start_date'],
                'end_date': o['end_date'],
                'source': 'csf',
                'csf_text': o['csf_text'],
            },
        )
        assert r.status_code == 200, r.text
    # A past month: monthly ones shown and overdue; the quarterly one ended in 2011.
    data = client.get('/api/fiscal-control/checklist', params={'year': 2025, 'month': 6}).json()
    items = {i['obligation_id']: i for i in data['companies'][0]['items']}
    assert set(items) == {'v11-iva-mensual', 'v11-iva-proveedores'}
    assert items['v11-iva-mensual']['due_date'] == '2025-07-17' and items['v11-iva-mensual']['overdue']
    assert data['summary'] == {'done': 0, 'total': 2, 'pending': 2, 'overdue': 2}
    mark = client.put(
        '/api/fiscal-control/checklist',
        json={
            'company_id': cid,
            'obligation_id': 'v11-iva-mensual',
            'year': 2025,
            'month': 6,
            'done': True,
            'revision': 0,
        },
    )
    assert mark.status_code == 200, mark.text
    again = client.put(
        '/api/fiscal-control/checklist',
        json={
            'company_id': cid,
            'obligation_id': 'v11-iva-mensual',
            'year': 2025,
            'month': 6,
            'done': True,
            'revision': 0,
        },
    )
    assert again.status_code == 409
    data = client.get('/api/fiscal-control/checklist', params={'year': 2025, 'month': 6}).json()
    done = next(i for i in data['companies'][0]['items'] if i['obligation_id'] == 'v11-iva-mensual')
    assert done['done'] and not done['overdue'] and done['marked_by'] == 'Administración de prueba'
    assert data['summary']['done'] == 1
    with SessionLocal() as db:
        row = db.execute(select(records).where(records.c.company_id == cid)).mappings().one()
        assert row['status'] == 'fulfilled' and row['period_id'] == '2025-06'
        assert db.execute(select(history.c.after).where(history.c.record_id == row['id'])).scalar()['done'] is True
    # Out of its dates or period, an obligation cannot be marked.
    bad = client.put(
        '/api/fiscal-control/checklist',
        json={
            'company_id': cid,
            'obligation_id': 'v11-isr-pm-trimestral',
            'year': 2025,
            'month': 6,
            'done': True,
            'revision': 0,
        },
    )
    assert bad.status_code == 422
    assert (
        client.get('/api/fiscal-control/checklist', params={'year': 2025, 'month': 6, 'pending': 'true'}).json()[
            'companies'
        ][0]['pending']
        == 1
    )
    xlsx = client.get('/api/fiscal-control/checklist.xlsx', params={'year': 2025, 'month': 6})
    assert xlsx.status_code == 200 and xlsx.content[:2] == b'PK'
    # The internal control matrix keeps only its own concepts.
    legacy = client.get('/api/fiscal-control', params={'year': 2025, 'month': 6}).json()
    assert not any(d['id'].startswith('v11-') for d in legacy['catalog'])


def test_only_admins_edit_the_catalog_and_auxiliaries_cannot_mark(client):  # noqa: F811
    cid = company(client, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(client)
    edit = {
        'official_name': 'Pago definitivo mensual de IVA.',
        'short_name': 'IVA',
        'group_name': 'IVA',
        'cadence': 'monthly',
        'due_rule': {'kind': 'day_next_month', 'day': 17},
        'aliases': ['IVA mensual.'],
    }
    assert client.put('/api/fiscal-control/catalog/v11-iva-mensual', json=edit).status_code == 200
    add_user(client, 'aux', grants=[(cid, 'read')])
    client.cookies.clear()
    login(client, 'aux')
    assert client.put('/api/fiscal-control/catalog/v11-iva-mensual', json=edit).status_code == 403
    assert (
        client.put(
            '/api/fiscal-control/checklist',
            json={
                'company_id': cid,
                'obligation_id': 'v11-iva-mensual',
                'year': 2025,
                'month': 6,
                'done': True,
                'revision': 0,
            },
        ).status_code
        == 403
    )


# ------------------------------------------------------------------ readers and traffic light (Cambio 1)


def test_compliance_readers_use_the_original_chain_and_flag_disagreements():
    sat = compliance_extract.analyze(sat_opinion_pdf())
    assert (sat['kind'], sat['fields']['result'], sat['fields']['folio']) == ('sat_opinion', 'positive', '26NA1234567')
    assert sat['fields']['issued_on'] == TODAY and not sat['review']
    negative = compliance_extract.analyze(sat_opinion_pdf(sense='N'))
    assert negative['fields']['result'] == 'negative'
    assert negative['fields']['omissions'][0]['name'].startswith('Declaración anual de ISR del ejercicio')
    tampered = compliance_extract.analyze(sat_opinion_pdf(tamper=True))
    assert tampered['review'] and 'cadena original' in tampered['warnings'][0]
    imss = compliance_extract.analyze(imss_pdf())
    assert (imss['fields']['result'], imss['fields']['workers'], imss['fields']['issued_on']) == ('positive', 3, TODAY)
    assert imss['fields']['official_valid_until'] == TODAY
    assert compliance_extract.analyze(imss_pdf(opinion='SIN OPINIÓN', workers=0))['fields']['result'] == 'no_opinion'
    info = compliance_extract.analyze(infonavit_pdf())
    assert (info['fields']['result'], info['fields']['workers'], info['fields']['folio']) == (
        'positive',
        9,
        f'123456/{TODAY.year}',
    )
    assert info['fields']['official_valid_until'] == TODAY + timedelta(days=30)
    assert info['fields']['bimester'] == f'{TODAY.year}-B4'
    debt = compliance_extract.analyze(infonavit_pdf(debt=True))
    assert debt['fields']['result'] == 'negative' and debt['review']
    assert compliance_extract.analyze(oracle_csf())['kind'] == 'csf'


def confirm(client, cid, data, payload):
    return client.post(
        f'/api/integral/companies/{cid}/compliance',
        files={'file': ('d.pdf', data, 'application/pdf')},
        data={'payload': json.dumps(payload, default=str)},
    )


def test_traffic_light_capture_validity_duplicates_and_not_applicable(client):  # noqa: F811
    cid = company(client, name='Servicios Sintéticos', rfc=RFC).json()['id']
    other = company(client, name='Otra', rfc='OTR010101AB1').json()['id']
    setup(client)
    status = client.get('/api/integral/document-status', params={'company_id': cid}).json()
    assert [light['state'] for light in status['companies'][0]['lights']] == ['gray'] * 5
    # Reading saves nothing; another company's RFC is refused.
    read = client.post(
        f'/api/integral/companies/{other}/compliance/analyze',
        files={'file': ('o.pdf', sat_opinion_pdf(), 'application/pdf')},
    ).json()
    assert read['rfc_mismatch'] and read['review']
    old = TODAY - timedelta(days=6)
    for data, payload in [
        (
            sat_opinion_pdf(issued=old),
            {'kind': 'sat_opinion', 'rfc': RFC, 'folio': '26NA1234567', 'issued_on': old, 'result': 'positive'},
        ),
        (
            imss_pdf(),
            {
                'kind': 'imss_opinion',
                'rfc': RFC,
                'folio': '12345678901234567890123',
                'issued_on': TODAY,
                'result': 'positive',
                'workers': 3,
            },
        ),
        (
            infonavit_pdf(workers=0),
            {
                'kind': 'infonavit',
                'rfc': RFC,
                'folio': f'123456/{TODAY.year}',
                'issued_on': TODAY,
                'result': 'positive',
                'workers': 0,
            },
        ),
    ]:
        r = confirm(client, cid, data, payload)
        assert r.status_code == 201, r.text
        assert r.json()['authority_validated'] is False
    dup = confirm(
        client,
        cid,
        sat_opinion_pdf(issued=old),
        {'kind': 'sat_opinion', 'rfc': RFC, 'folio': '26NA1234567', 'issued_on': old, 'result': 'positive'},
    )
    assert dup.status_code == 409
    lights = {
        light['kind']: light
        for light in client.get('/api/integral/document-status', params={'company_id': cid}).json()['companies'][0][
            'lights'
        ]
    }
    assert lights['sat']['state'] == 'amber' and lights['sat']['source'] == 'document'  # 6 days: amber (5/7)
    assert lights['imss']['state'] == 'green' and lights['imss']['workers'] == 3
    assert lights['infonavit']['propose_not_applicable']
    assert (
        client.put(
            f'/api/integral/companies/{cid}/document-settings', json={'kind': 'infonavit', 'not_applicable': True}
        ).status_code
        == 200
    )
    assert (
        client.put(
            '/api/integral/document-validity', json={'kind': 'sat', 'green_days': 7, 'amber_days': 10}
        ).status_code
        == 200
    )
    body = client.get('/api/integral/document-status', params={'company_id': cid}).json()
    lights = {light['kind']: light for light in body['companies'][0]['lights']}
    assert lights['sat']['state'] == 'green' and lights['infonavit']['state'] == 'na'
    # A negative opinion is red even when recent, and its omission is shown on the obligation.
    client.put(
        '/api/fiscal-control/applicability',
        json={'company_id': cid, 'obligation_id': 'v11-anual-pm-general', 'applicable': True, 'revision': 0},
    )
    neg = confirm(
        client,
        cid,
        sat_opinion_pdf(sense='N', folio='26NA7654321'),
        {
            'kind': 'sat_opinion',
            'rfc': RFC,
            'folio': '26NA7654321',
            'issued_on': TODAY,
            'result': 'negative',
            'omissions': [
                {
                    'name': 'Declaración anual de ISR del ejercicio Personas morales.',
                    'year': TODAY.year - 1,
                    'obligation_id': 'v11-anual-pm-general',
                }
            ],
        },
    )
    assert neg.status_code == 201, neg.text
    body = client.get('/api/integral/document-status').json()
    mine = next(c for c in body['companies'] if c['company_id'] == cid)
    assert next(light for light in mine['lights'] if light['kind'] == 'sat')['state'] == 'red'
    summary = body['summary']
    assert summary['active_rfcs'] == 2 and summary['sat']['negative'] == 1
    items = client.get(
        '/api/fiscal-control/checklist', params={'year': TODAY.year - 1, 'month': 12, 'company_id': cid}
    ).json()['companies'][0]['items']
    assert next(i for i in items if i['obligation_id'] == 'v11-anual-pm-general')['opinion_omissions'] == [
        TODAY.year - 1
    ]
    assert 'validad' not in json.dumps(body).replace('authority_validated', '')


# ------------------------------------------------------------------ CFDI calendar (Cambio 3)


def cfdi(issuer, receiver, day, total, uuid):
    return (
        '<?xml version="1.0" encoding="UTF-8"?><cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        f'Version="4.0" Fecha="{day}T10:00:00" Total="{total}" Moneda="MXN" TipoDeComprobante="I">'
        f'<cfdi:Emisor Rfc="{issuer}" Nombre="A" RegimenFiscal="601"/><cfdi:Receptor Rfc="{receiver}" Nombre="B"/>'
        '<cfdi:Complemento><tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" '
        f'UUID="{uuid}" FechaTimbrado="{day}T10:05:00"/></cfdi:Complemento></cfdi:Comprobante>'
    ).encode()


def test_cfdi_calendar_counts_issued_and_received_by_month_and_day(client):  # noqa: F811
    cid = company(client, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(client)
    files = [
        cfdi(RFC, 'XAXX010101000', '2026-01-15', '1160.00', '11111111-1111-1111-1111-111111111111'),
        cfdi(RFC, 'XAXX010101000', '2026-01-15', '100.00', '22222222-2222-2222-2222-222222222222'),
        cfdi('OTR010101AB1', RFC, '2026-03-02', '50.50', '33333333-3333-3333-3333-333333333333'),
    ]
    for i, data in enumerate(files):
        r = client.post(
            '/api/storage/documents', files={'file': (f'f{i}.xml', data, 'application/xml')}, data={'company_id': cid}
        )
        assert r.status_code in (200, 201), r.text
    year = client.get(f'/api/cfdi-calendar/{cid}', params={'year': 2026, 'month': 1}).json()
    jan, mar = year['months'][0], year['months'][2]
    assert jan['issued'] == {'count': 2, 'total': 1260.0} and jan['received']['count'] == 0
    assert mar['received'] == {'count': 1, 'total': 50.5} and mar['issued']['count'] == 0
    assert year['days'][14]['issued']['count'] == 2 and year['days'][13]['issued']['count'] == 0
    listed = client.get(f'/api/cfdi-calendar/{cid}/documents', params={'day': '2026-01-15', 'kind': 'issued'}).json()
    assert {r['counterpart_rfc'] for r in listed} == {'XAXX010101000'} and len(listed) == 2
    assert client.get(f'/api/cfdi-calendar/{cid}', params={'year': 2025}).json()['months'][0]['issued']['count'] == 0
    rebuilt = client.post(f'/api/cfdi-calendar/{cid}/rebuild').json()
    assert rebuilt['indexed'] == 0  # everything was indexed on entry


# ------------------------------------------------------------------ password manager (Cambio 4)


@pytest.fixture
def keyring(monkeypatch):
    monkeypatch.setenv('CONTA_VAULT_KEYRING', json.dumps({'k1': base64.b64encode(os.urandom(32)).decode()}))
    monkeypatch.setenv('CONTA_VAULT_ACTIVE_KEY', 'k1')


def test_envelope_v2_strength_and_fingerprint():
    c = VaultCipher({'k1': os.urandom(32)}, 'k1')
    sealed = c.seal('Secreto-Sintetico-1!', 'c', 'r')
    assert sealed['v'] == 2 and 'Secreto' not in json.dumps(sealed)
    assert c.open(sealed, 'c', 'r', authorize_recent=lambda: True) == 'Secreto-Sintetico-1!'
    assert c.fingerprint('a') == c.fingerprint('a') != c.fingerprint('b')
    assert strength('123456') <= 1 and strength('Secr3to!Largo2026') == 4 and strength('ssb100abcdefgh', RFC) <= 1


def test_reveal_needs_permission_and_recent_reauth_and_is_logged(client, keyring):  # noqa: F811
    cid = company(client, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(client)
    made = client.post(
        f'/api/credentials/companies/{cid}/secrets',
        json={'service_id': 'sat_password', 'secret': 'Secreto-Sintetico-1!', 'username': RFC},
    )
    assert made.status_code == 200, made.text
    ident = made.json()['id']
    client.post(
        f'/api/credentials/companies/{cid}/secrets', json={'service_id': 'idse', 'secret': 'Secreto-Sintetico-1!'}
    )
    listed = client.get('/api/credentials/vault').json()
    assert listed['health']['repeated'] == 2 and 'Secreto' not in json.dumps(listed)
    assert listed['items'][0]['username'] in (RFC, None)
    assert client.post(f'/api/credentials/companies/{cid}/secrets/{ident}/reveal', json={}).status_code == 428
    assert client.post('/api/credentials/reauth', json={'password': 'wrong'}).status_code == 403
    assert client.post('/api/credentials/reauth', json={'password': PASSWORD}).status_code == 200
    shown = client.post(
        f'/api/credentials/companies/{cid}/secrets/{ident}/reveal', json={'action': 'copy', 'reason': 'x'}
    )
    assert shown.status_code == 200 and shown.json()['secret'] == 'Secreto-Sintetico-1!'
    assert 'no-store' in shown.headers['cache-control']
    # Editing the visible data keeps the password.
    edit = client.post(
        f'/api/credentials/companies/{cid}/secrets',
        params={'ident': ident},
        json={'service_id': 'sat_password', 'revision': 1, 'notes': 'nota'},
    )
    assert edit.status_code == 200, edit.text
    assert (
        client.post(f'/api/credentials/companies/{cid}/secrets/{ident}/reveal').json()['secret']
        == 'Secreto-Sintetico-1!'
    )
    with SessionLocal() as db:
        actions = set(db.scalars(select(audit.c.action).where(audit.c.record_id == ident)))
        assert {'reveal_blocked', 'secret_copied', 'secret_revealed'} <= actions
    # An auxiliar with company access but without the explicit grant cannot see it.
    add_user(client, 'aux', grants=[(cid, 'write')])
    client.cookies.clear()
    login(client, 'aux')
    client.post('/api/credentials/reauth', json={'password': PASSWORD})
    assert client.post(f'/api/credentials/companies/{cid}/secrets/{ident}/reveal').status_code == 403


def test_single_use_ticket_for_the_extension(client, keyring):  # noqa: F811
    cid = company(client, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(client)
    ident = client.post(
        f'/api/credentials/companies/{cid}/secrets',
        json={'service_id': 'sat_password', 'secret': 'Secreto-Sintetico-1!'},
    ).json()['id']
    assert (
        client.post(
            f'/api/credentials/companies/{cid}/secrets/{ident}/ticket', json={'purpose': 'sat_password'}
        ).status_code
        == 428
    )
    client.post('/api/credentials/reauth', json={'password': PASSWORD})
    ticket = client.post(
        f'/api/credentials/companies/{cid}/secrets/{ident}/ticket', json={'purpose': 'sat_password'}
    ).json()['ticket']
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as extension:  # no session: the ticket alone
        used = extension.post('/api/credentials/tickets/redeem', json={'ticket': ticket})
        assert used.status_code == 200 and used.json()['password'] == 'Secreto-Sintetico-1!'
        assert used.json()['rfc'] == RFC
        assert extension.post('/api/credentials/tickets/redeem', json={'ticket': ticket}).status_code == 410
    fiel = client.post(
        f'/api/credentials/companies/{cid}/secrets', json={'service_id': 'fiel', 'secret': 'Clave-FIEL-Sintetica-9'}
    ).json()['id']
    assert (
        client.post(f'/api/credentials/companies/{cid}/secrets/{fiel}/ticket', json={'purpose': 'sat_fiel'}).status_code
        == 422
    )  # needs .cer and .key


def workbook(sheets):
    book = Workbook()
    book.remove(book.active)
    for title, rows in sheets.items():
        sheet = book.create_sheet(title)
        for r in rows:
            sheet.append(r)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_import_of_both_excel_formats_never_shows_passwords(client, keyring):  # noqa: F811
    cid = company(client, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(client)
    office = workbook(
        {
            'Hoja1': [
                [
                    'No.',
                    'Empresa',
                    'RFC',
                    'Régimen',
                    'Contraseña',
                    'Contraseña FIEL',
                    'Fecha inicial',
                    'IDSE',
                    'Créditos',
                ],
                [
                    1,
                    'Servicios Sintéticos',
                    RFC,
                    'GENERAL P.M',
                    'Ciec-Sintetica-1 (cambió en mayo)',
                    'Fiel-Sint-2',
                    '2024-01-01',
                    'usuario.idse / Idse-Sint-3',
                    'Credito-Sint-4',
                ],
                [2, 'Sin empresa', 'NOEX010101AB1', 'PF', 'Otra-Sint-5', None, None, None, None],
            ]
        }
    )
    preview = client.post(
        '/api/credentials/import/preview', files={'file': ('a.xlsx', office, 'application/octet-stream')}
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert not any(v in json.dumps(body) for v in ('Ciec-Sintetica-1', 'Fiel-Sint-2', 'Idse-Sint-3', 'usuario.idse'))
    first, second = body['rows']
    assert first['company_id'] == cid and first['importable']
    assert {e['service_id'] for e in first['entries']} == {'sat_password', 'fiel', 'idse', 'other'}
    assert not second['importable'] and second['issues']
    done = client.post(
        '/api/credentials/import/confirm',
        files={'file': ('a.xlsx', office, 'application/octet-stream')},
        data={'sha256': body['sha256'], 'rows': str(first['row'])},
    )
    assert done.status_code == 200, done.text
    assert done.json()['created'] == 4
    with SessionLocal() as db:
        rows = {
            r['service_id']: r
            for r in db.execute(select(credentials).where(credentials.c.company_id == cid)).mappings()
        }
    assert rows['idse']['username'] == 'usuario.idse' and rows['sat_password']['notes'] == 'cambió en mayo'
    # Corporate format: EMPRESAS + CONTRASEÑAS joined by RFC; existing credentials are kept.
    corporate = workbook(
        {
            'EMPRESAS': [
                ['No.', 'Empresa', 'RFC', 'Régimen', 'Giro', 'Nivel', 'REPSE', 'Trabajadores', 'Representante legal'],
                [1, 'Servicios Sintéticos', RFC, 'GENERAL', 'Comercio', 'A', 'SI', '12', 'Persona Ficticia'],
            ],
            'CONTRASEÑAS': [
                ['No.', 'Empresa', 'RFC', 'Nivel', 'Contraseña', 'FIEL de la empresa', 'FIEL del representante'],
                [1, 'Servicios Sintéticos', RFC, 'A', 'Ciec-Sintetica-1', 'Fiel-Sint-2', 'Fiel-Rep-6'],
            ],
        }
    )
    body = client.post(
        '/api/credentials/import/preview', files={'file': ('b.xlsx', corporate, 'application/octet-stream')}
    ).json()
    row = body['rows'][0]
    assert set(row['sheets']) == {'EMPRESAS', 'CONTRASEÑAS'}
    assert {(e['service_id'], e['holder']) for e in row['entries']} >= {('fiel', 'legal_rep'), ('fiel', 'company')}
    result = client.post(
        '/api/credentials/import/confirm',
        files={'file': ('b.xlsx', corporate, 'application/octet-stream')},
        data={'sha256': body['sha256'], 'rows': str(row['row'])},
    ).json()
    assert result['created'] == 1 and result['kept_existing'] == 2  # only the representative's FIEL is new
    from app.models import Company

    with SessionLocal() as db:
        c = db.get(Company, cid)
        assert (c.workers, c.repse, c.business_activity) == (12, True, 'Comercio')


def test_export_is_for_admins_with_reauth(client, keyring):  # noqa: F811
    cid = company(client, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(client)
    client.post(
        f'/api/credentials/companies/{cid}/secrets', json={'service_id': 'sat_password', 'secret': 'Sec-1-Sint!'}
    )
    assert client.post('/api/credentials/export', json={'reason': 'respaldo'}).status_code == 428
    client.post('/api/credentials/reauth', json={'password': PASSWORD})
    out = client.post('/api/credentials/export', json={'reason': 'respaldo'})
    assert out.status_code == 200 and out.content[:2] == b'PK'
