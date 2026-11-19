"""Content review of Organizador CFDI plans with synthetic files built by the test (cambios 5.1 to 5.3)."""

import io

from reportlab.pdfgen import canvas

from app import organizador_engine as motor
from app.organizador_review import foreign_rfc_folders, omitted_files, review

RFC = 'AAA010101AA1'
OTHER = 'BBB020202BB2'
U1 = '11111111-2222-3333-4444-555555555501'
U2 = '11111111-2222-3333-4444-555555555502'
U3 = '11111111-2222-3333-4444-555555555503'
U4 = '11111111-2222-3333-4444-555555555504'
U5 = '11111111-2222-3333-4444-555555555505'


def pdf(*lines):
    stream = io.BytesIO()
    c = canvas.Canvas(stream)
    y = 750
    for line in lines:
        c.drawString(50, y, line)
        y -= 20
    c.showPage()
    c.save()
    return stream.getvalue()


def xml(uuid, emisor=RFC, receptor=OTHER, fecha='2026-04-10'):
    return (
        f'<Comprobante TipoDeComprobante="I" Fecha="{fecha}T10:00:00" Total="1234.56">'
        f'<Emisor Rfc="{emisor}"/><Receptor Rfc="{receptor}"/><TimbreFiscalDigital UUID="{uuid}"/></Comprobante>'
    ).encode()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def build(tmp_path):
    base = tmp_path / 'base'
    e = base / 'Emitidos' / RFC / '2026-04'
    r = base / 'Recibidos' / RFC / '2026-04'
    write(e / 'bien.xml', xml(U1))
    write(e / 'bien.pdf', pdf('Factura', U1))
    write(e / 'mes.xml', xml(U2, fecha='2026-05-02'))  # XML dated in May, filed under April
    write(r / 'ajena.xml', xml(U3, emisor=OTHER, receptor=OTHER))  # a Recibido whose receiver is not the company
    write(e / 'nombre.xml', xml(U4))
    write(e / 'nombre.pdf', pdf('Otra factura', U5))  # same name, another UUID: not a pair
    write(e / 'sinsolo.pdf', pdf())  # a PDF with no text at all
    write(e / 'huerfano.xml', xml(U5))  # XML without any PDF carrying its UUID... except nombre.pdf: it carries U5
    write(e / 'roto.xml', b'esto no es xml')
    write(base / 'Emitidos' / OTHER / '2026-04' / 'otra.xml', xml(U1, emisor=OTHER))  # another RFC's folder
    write(base / 'Emitidos' / RFC / '2026-04' / 'sub' / 'x.xml', xml(U1))
    write(base / 'Emitidos' / RFC / '2026-07' / 'julio.xml', xml(U1, fecha='2026-07-01'))
    write(e / 'nota.txt', b'texto')
    return base


def plan_for(tmp_path):
    base = build(tmp_path)
    return motor.analyze(
        motor.Options(
            source=str(base), destination=str(tmp_path / 'out'), rfc=RFC, year=2026, months=(4, 5), operation='copy'
        )
    )


def test_incoherences_are_found_in_the_content_not_the_folder(tmp_path):
    rows = review(plan_for(tmp_path))
    by = {r['name']: r for r in rows.values()}
    assert by['bien.xml']['incoherence'] == [] and by['bien.xml']['uuid'] == U1
    assert by['mes.xml']['incoherence'] == ['periodo_distinto']
    assert by['ajena.xml']['incoherence'] == ['receptor_distinto']
    assert by['roto.xml']['incoherence'] == ['xml_ilegible']
    # An amount is never read or exposed.
    assert '1234.56' not in str(rows)


def test_pairs_only_by_uuid_in_the_pdf_text_never_by_name(tmp_path):
    rows = review(plan_for(tmp_path))
    by = {r['name']: r for r in rows.values()}
    assert by['bien.pdf']['pair'] == 'identificada' and by['bien.xml']['partner'].endswith('bien.pdf')
    # nombre.xml / nombre.pdf share the name but the PDF carries another UUID: no pair by name.
    assert by['nombre.xml']['pair'] == 'sin_pareja_identificada' and 'xml_sin_pdf' in by['nombre.xml']['warnings']
    assert by['nombre.pdf']['partner'].endswith('huerfano.xml')  # its text carries U5, the other XML
    assert by['sinsolo.pdf']['pair'] == 'sin_pareja_identificada' and 'pdf_sin_xml' in by['sinsolo.pdf']['warnings']


def test_a_pdf_paired_to_an_incoherent_xml_is_blocked_too(tmp_path):
    base = tmp_path / 'base'
    e = base / 'Emitidos' / RFC / '2026-04'
    write(e / 'a.xml', xml(U1, fecha='2026-06-01'))
    write(e / 'a.pdf', pdf('Factura', U1))
    plan = motor.analyze(
        motor.Options(
            source=str(base), destination=str(tmp_path / 'o'), rfc=RFC, year=2026, months=(4,), operation='copy'
        )
    )
    rows = {r['name']: r for r in review(plan).values()}
    assert rows['a.pdf']['incoherence'] == ['pareja_bloqueada'] and rows['a.xml']['incoherence'] == ['periodo_distinto']


def test_omitted_files_have_a_reason_and_foreign_rfc_folders_are_reported(tmp_path):
    plan = plan_for(tmp_path)
    reasons = {Path_name(x['path']): x['reason'] for x in omitted_files(plan)}
    assert reasons['otra.xml'] == 'otro_rfc'
    assert reasons['x.xml'] == 'subcarpeta'
    assert reasons['julio.xml'] == 'mes_no_elegido'
    assert reasons['nota.txt'] == 'extension'
    assert foreign_rfc_folders(tmp_path / 'base', RFC) == [OTHER]


def Path_name(path):  # noqa: N802 - tiny helper kept next to its only use
    return path.rsplit('/', 1)[-1]
