"""Enrichment of Recopila analyses with synthetic documents built by the test (cambios 4.1, 4.2 and 4.7)."""

import io

from reportlab.pdfgen import canvas

from app import recopila_engine as motor
from app.recopila_enrich import apply_adjustments, build

RFC = 'AAA010101AA1'
FOREIGN = 'ZZZ999999ZZ9'
A = '11111111-2222-3333-4444-aaaaaaaaaaa1'.upper()
B1 = '11111111-2222-3333-4444-bbbbbbbbbbb1'.upper()
B2 = '11111111-2222-3333-4444-bbbbbbbbbbb2'.upper()
C = '11111111-2222-3333-4444-ccccccccccc1'.upper()
P = '11111111-2222-3333-4444-ddddddddddd1'.upper()
D = '11111111-2222-3333-4444-eeeeeeeeeee1'.upper()
F = '11111111-2222-3333-4444-fffffffffff1'.upper()
G = '11111111-2222-3333-4444-111111111111'.upper()
OTHER_TEXT = '11111111-2222-3333-4444-999999999999'.upper()
LEFT = '11111111-2222-3333-4444-777777777777'.upper()


def pdf(*pages):
    stream = io.BytesIO()
    c = canvas.Canvas(stream)
    for lines in pages:
        y = 750
        for line in lines:
            c.drawString(50, y, line)
            y -= 20
        c.showPage()
    c.save()
    return stream.getvalue()


def policy(kind, date, *uuids):
    return ['IMPRESO DE POLIZAS', kind, f'Fecha {date}', 'Descripcion prueba', 'CFDI asociados a la poliza', *uuids]


def xml(uuid, emisor='BBB020202BB2', receptor=RFC, tipo='I', fecha='2026-10-01', related=()):
    complement = ''
    if related:
        docs = ''.join(f'<DoctoRelacionado IdDocumento="{u}"/>' for u in related)
        complement = f'<Complemento><Pagos><Pago>{docs}</Pago></Pagos></Complemento>'
    return (
        f'<Comprobante TipoDeComprobante="{tipo}" Fecha="{fecha}T10:00:00" Serie="S" Folio="9" MetodoPago="PUE" Total="999.99">'
        f'<Emisor Rfc="{emisor}"/><Receptor Rfc="{receptor}" UsoCFDI="G03"/>{complement}'
        f'<TimbreFiscalDigital UUID="{uuid}"/></Comprobante>'
    ).encode()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def folder(tmp_path):
    root = tmp_path / 'entrada'
    # Complete: A has XML and a PDF whose text carries its UUID.
    write(root / 'CFDI' / f'{A}.xml', xml(A))
    write(root / 'CFDI' / f'{A}.pdf', pdf(['Factura', A]))
    # Partial: B1 supported, B2 does not exist anywhere.
    write(root / 'CFDI' / f'{B1}.xml', xml(B1))
    write(root / 'CFDI' / f'{B1}.pdf', pdf(['Factura', B1]))
    # XML without PDF.
    write(root / 'CFDI' / f'{C}.xml', xml(C))
    # Complement whose own UUID is listed in the Pago policy (no related invoice is in the policy).
    write(root / 'CFDI' / f'{P}.xml', xml(P, tipo='P', related=[A]))
    write(root / 'CFDI' / f'{P}.pdf', pdf(['Complemento', P]))
    # CFDI listed in a Diario policy.
    write(root / 'CFDI' / f'{D}.xml', xml(D))
    write(root / 'CFDI' / f'{D}.pdf', pdf(['Factura diario', D]))
    # Foreign RFC: neither issuer nor receiver is the company.
    write(root / 'CFDI' / f'{F}.xml', xml(F, emisor=FOREIGN, receptor='YYY010101YY1'))
    write(root / 'CFDI' / f'{F}.pdf', pdf(['Factura ajena', F]))
    # Same file name, another UUID in the PDF text: the pair is not verified.
    write(root / 'CFDI' / f'{G}.xml', xml(G, fecha='2026-12-05'))
    write(root / 'CFDI' / f'{G}.pdf', pdf(['Otra factura', OTHER_TEXT]))
    # A leftover from another period.
    write(root / 'CFDI' / f'{LEFT}.xml', xml(LEFT, fecha='2025-01-02'))
    write(root / 'CFDI' / f'{LEFT}.pdf', pdf(['Vieja', LEFT]))
    # A two-page policy file plus single policies.
    write(
        root / 'Polizas' / 'octubre.pdf',
        pdf(
            policy('Compra (Egreso)', '05/10/2026', A),
            policy('Compra (Egreso)', '06/10/2026', B1, B2),
        ),
    )
    write(root / 'Polizas' / 'otras.pdf', pdf(policy('Compra (Egreso)', '07/10/2026', C)))
    write(root / 'Polizas' / 'pago.pdf', pdf(policy('Pago (Egreso)', '08/10/2026', P)))
    write(root / 'Polizas' / 'diario.pdf', pdf(policy('Diario (Manual)', '09/10/2026', D)))
    write(root / 'Polizas' / 'ajena.pdf', pdf(policy('Compra (Egreso)', '10/10/2026', F)))
    write(root / 'Polizas' / 'nombre.pdf', pdf(policy('Compra (Egreso)', '11/10/2026', G)))
    # A format the engine cannot read: detected only, never parsed.
    write(root / 'Otros' / 'contalink.pdf', pdf(['Contalink', 'Póliza de diario', 'Cuenta Debe Haber'] * 1))
    return root


def analysis(tmp_path):
    root = folder(tmp_path)
    return motor.analyze(root, tmp_path / 'work')


def status_of(result, enrichment, source_name, page, uuid):
    for index, pol in enumerate(result.policies):
        if pol.source_pdf.endswith(source_name) and pol.page == page and uuid in pol.uuids:
            return enrichment['policies'][index]
    raise AssertionError('policy not found')


def test_statuses_two_page_policy_and_missing_uuids(tmp_path):
    result = analysis(tmp_path)
    data = build(result, RFC)
    assert status_of(result, data, 'octubre.pdf', 1, A)['status'] == 'Completa'
    partial = status_of(result, data, 'octubre.pdf', 2, B1)
    assert partial['status'] == 'Parcial' and partial['missing'] == [B2] and partial['supported'] == [B1]
    xml_only = status_of(result, data, 'otras.pdf', 1, C)
    assert xml_only['status'] == 'XML sin PDF' and xml_only['missing'] == [C]
    assert status_of(result, data, 'pago.pdf', 1, P)['status'] == 'Sin soporte'


def test_extra_searches_are_proposals_not_relations(tmp_path):
    result = analysis(tmp_path)
    data = build(result, RFC)
    kinds = {(p['kind'], p['uuid']) for p in data['proposals']}
    assert ('complemento_directo', P) in kinds and ('diario', D) in kinds
    pago = next(p for p in result.policies if p.policy_type == 'Pago (Egreso)')
    assert pago.matched_pdfs == []  # the engine's result is untouched by the enrichment
    assert all(not p['pdf'].startswith(('/', 'C:')) for p in data['proposals'])


def test_foreign_rfc_unverified_pair_and_leftover_categories(tmp_path):
    result = analysis(tmp_path)
    data = build(result, RFC)
    foreign = {r['uuid'] for r in data['review'] if r['kind'] == 'rfc_ajeno'}
    assert F in foreign and A not in foreign
    unverified = {r['uuid'] for r in data['review'] if r['kind'] == 'pareja_no_verificada'}
    assert G in unverified and A not in unverified
    assert data['cfdis'][G]['pareja'] == 'no_verificada' and data['cfdis'][A]['pareja'] == 'verificada'
    categories = {item['uuid']: item['category'] for item in data['leftovers']}
    assert categories[LEFT] == 'otro_periodo'
    assert categories[P] == 'complementos'
    # Without a company RFC nothing is compared against it.
    assert not [r for r in build(result, '')['review'] if r['kind'] == 'rfc_ajeno']


def test_amounts_are_never_exposed_and_months_summarize(tmp_path):
    result = analysis(tmp_path)
    data = build(result, RFC)
    assert '999.99' not in str(data) and data['cfdis'][A]['metodo_pago'] == 'PUE' and data['cfdis'][A]['uso'] == 'G03'
    october = data['months']['2026-10']
    assert october['policies'] == 7 and october['Completa'] >= 1 and october['Parcial'] == 1
    assert data['cfdis'][A]['serie'] == 'S' and data['cfdis'][A]['folio'] == '9'


def test_incompatible_format_is_only_detected(tmp_path):
    result = analysis(tmp_path)
    data = build(result, RFC)
    assert data['unsupported']['pages'] >= 1 and data['unsupported']['contalink_hint'] is True
    assert all('contalink' not in p.source_pdf for p in result.policies)


def test_adjustments_attach_and_remove_without_touching_the_engine(tmp_path):
    result = analysis(tmp_path)
    data = build(result, RFC)
    proposal = next(p for p in data['proposals'] if p['kind'] == 'diario')
    index = proposal['policy_index']
    apply_adjustments(
        result, [{'policy_idx': index, 'action': 'attach', 'target': proposal['pdf'], 'revoked_at': None}]
    )
    pol = result.policies[index]
    assert [p.endswith(f'{D}.pdf') for p in pol.matched_pdfs] == [True] and pol.match_status == 'RELACIONADO'
    assert not any(x.endswith(f'{D}.pdf') for x in result.leftovers)
    apply_adjustments(
        result, [{'policy_idx': index, 'action': 'remove', 'target': proposal['pdf'], 'revoked_at': None}]
    )
    assert pol.matched_pdfs == [] and any(x.endswith(f'{D}.pdf') for x in result.leftovers)
    # A revoked adjustment or an unknown policy is ignored; a path outside the analysis is never attached.
    apply_adjustments(result, [{'policy_idx': index, 'action': 'attach', 'target': proposal['pdf'], 'revoked_at': 'x'}])
    apply_adjustments(result, [{'policy_idx': 999, 'action': 'attach', 'target': proposal['pdf'], 'revoked_at': None}])
    apply_adjustments(result, [{'policy_idx': index, 'action': 'attach', 'target': '../../x.pdf', 'revoked_at': None}])
    assert pol.matched_pdfs == []
