import struct
from datetime import datetime, timedelta, timezone

import pytest

from app.cert_groups import CertIndex, certificate_info, holder_kind
from app.sat_reconcile import PpdIndex, SatReconcile, parse_payment, parse_report
from app.xls_reader import read_rows

U1 = 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'
U2 = 'BBBBBBBB-BBBB-4BBB-8BBB-BBBBBBBBBBBB'
U3 = 'CCCCCCCC-CCCC-4CCC-8CCC-CCCCCCCCCCCC'


def record(rid, body):
    return struct.pack('<HH', rid, len(body)) + body


def build_xls(rows):
    """A tiny BIFF8 workbook inside an OLE2 container (regular sectors), enough to exercise the reader."""
    strings = [c for row in rows for c in row if isinstance(c, str)]
    sst = struct.pack('<II', len(strings), len(strings))
    for text in strings:
        sst += struct.pack('<HB', len(text), 0) + text.encode('latin-1')
    book = record(0x0809, struct.pack('<HHHH', 0x0600, 0x0005, 0, 0)) + record(0x00FC, sst) + record(0x000A, b'')
    book += record(0x0809, struct.pack('<HHHH', 0x0600, 0x0010, 0, 0))
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if isinstance(cell, str):
                book += record(0x00FD, struct.pack('<HHHI', r, c, 0, strings.index(cell)))
            elif isinstance(cell, float):
                book += record(0x0203, struct.pack('<HHHd', r, c, 0, cell))
            elif isinstance(cell, int):  # RK integer
                book += record(0x027E, struct.pack('<HHHI', r, c, 0, (cell << 2) | 2))
    book += record(0x000A, b'')
    while len(book) < 4200:  # unknown records are ignored; this keeps the stream out of the mini stream
        book += record(0x1234, b'\x00' * 60)
    sectors = (len(book) + 511) // 512
    header = bytearray(512)
    header[:8] = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
    struct.pack_into('<HH', header, 0x1E, 9, 6)
    struct.pack_into('<I', header, 0x2C, 1)
    struct.pack_into('<I', header, 0x30, 1)
    struct.pack_into('<I', header, 0x38, 4096)
    struct.pack_into('<I', header, 0x3C, 0xFFFFFFFE)
    struct.pack_into('<I', header, 0x44, 0xFFFFFFFE)
    struct.pack_into('<I', header, 0x4C, 0)
    struct.pack_into('<108I', header, 0x50, *([0xFFFFFFFF] * 108))
    fat = [0xFFFFFFFD, 0xFFFFFFFE] + [n + 3 for n in range(sectors - 1)] + [0xFFFFFFFE]
    fat_sector = struct.pack('<128I', *(fat + [0xFFFFFFFF] * (128 - len(fat))))
    root = 'Root Entry'.encode('utf-16le') + b'\x00\x00'
    workbook = 'Workbook'.encode('utf-16le') + b'\x00\x00'
    entry0 = root.ljust(64, b'\x00') + struct.pack('<HBB', len(root), 5, 1) + b'\xff' * 12 + b'\x00' * 16
    entry0 = entry0.ljust(116, b'\x00') + struct.pack('<II', 0xFFFFFFFE, 0) + b'\x00' * 4
    entry1 = workbook.ljust(64, b'\x00') + struct.pack('<HBB', len(workbook), 2, 1) + b'\xff' * 12 + b'\x00' * 16
    entry1 = entry1.ljust(116, b'\x00') + struct.pack('<II', 2, len(book)) + b'\x00' * 4
    directory = (entry0 + entry1).ljust(512, b'\x00')
    return bytes(header) + fat_sector + directory + book.ljust(sectors * 512, b'\x00')


def test_xls_reader_reads_text_and_numbers():
    rows = [['UUID', 'Total', 'Fecha'], [U1, 1234.5, '2026-07-02'], [U2, 7, 'x']]
    assert read_rows(build_xls(rows)) == rows


def test_xls_reader_rejects_garbage():
    for data in (b'', b'not an xls file at all', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\x00' * 100):
        with pytest.raises(ValueError):
            read_rows(data)


def report_rows(*uuids):
    rows = [['XML', 'Rfc Emisor', 'Rfc Receptor', 'Tipo', 'Fecha', 'Total', 'UUID', 'Estatus']]
    for n, uuid in enumerate(uuids):
        status = 'Cancelado' if n == 2 else None
        rows.append([uuid, 'AAA010101AAA', 'BBB010101BBB', 'ingreso', '2026-07-02T10:00:00', 100.0, uuid, status])
    return rows


def test_report_versus_xml_finds_missing_and_extra():
    recon = SatReconcile()
    recon.add_report('R', 2026, 7, report_rows(U1, U2))
    recon.add_xml(U1, 'CFDI/a.xml', {'k': 'R', 'y': 2026, 'm': 7})
    recon.add_xml(U3, 'CFDI/c.xml', {'k': 'R', 'y': 2026, 'm': 7})  # in the folder, not in the report
    recon.add_xml(U1, 'CFDI/x.xml', {'k': 'E', 'y': 2026, 'm': 8})  # a month with XML but no report
    out = recon.result()
    july = next(p for p in out['periodos'] if p['m'] == 7)
    assert (july['ok'], july['n_faltan'], july['n_sobran'], july['s']) == (1, 1, 1, 'revisar')
    assert july['faltan'][0]['u'] == U2 and july['faltan'][0]['total'] == 100.0
    assert next(p for p in out['periodos'] if p['m'] == 8)['s'] == 'sin_reporte_mes'
    assert out['faltan_xml'] == 1 and out['sin_reporte_xml'] == 1


def test_canceled_status_in_report_flags_the_month():
    recon = SatReconcile()
    recon.add_report('E', 2026, 7, report_rows(U1, U2, U3))  # the third row is «Cancelado»
    for uuid in (U1, U2, U3):
        recon.add_xml(uuid, uuid + '.xml', {'k': 'E', 'y': 2026, 'm': 7})
    july = recon.result()['periodos'][0]
    assert july['cancelados'] == 1 and july['s'] == 'revisar'
    assert parse_report([['sin encabezado']]) == []


PAYMENT = (
    '<pago20:Pago><pago20:DoctoRelacionado IdDocumento="%s" NumParcialidad="1" ImpPagado="40.00" '
    'ImpSaldoInsoluto="60.00"/></pago20:Pago>'
)


def test_ppd_invoices_and_their_payments():
    assert parse_payment(PAYMENT % U1) == [(U1, 40.0, 60.0, 1)]
    ppd = PpdIndex()
    place = {'k': 'E', 'y': 2026, 'm': 7}
    for uuid in (U1, U2, U3):
        ppd.add_invoice(uuid, uuid + '.xml', {'metodo': 'PPD', 'tipo': 'I', 'total': 100.0}, place)
    ppd.add_invoice(
        'D' * 8 + '-DDDD-4DDD-8DDD-' + 'D' * 12, 'pue.xml', {'metodo': 'PUE', 'tipo': 'I', 'total': 5.0}, place
    )
    ppd.add_payment('pago1.xml', PAYMENT % U1)
    ppd.add_payment(
        'pago2.xml',
        '<pago20:DoctoRelacionado IdDocumento="%s" NumParcialidad="2" ImpPagado="60.00" ImpSaldoInsoluto="0.00"/>' % U1
        + '<pago20:DoctoRelacionado IdDocumento="%s" NumParcialidad="1" ImpPagado="10.00" ImpSaldoInsoluto="90.00"/>'
        % U2
        + '<pago20:DoctoRelacionado IdDocumento="EEEEEEEE-EEEE-4EEE-8EEE-EEEEEEEEEEEE" NumParcialidad="1" ImpPagado="1" ImpSaldoInsoluto="0"/>',
    )
    out = ppd.result()
    states = {r['u']: r['s'] for r in out['rows']}
    assert states == {U1: 'liquidada', U2: 'parcial', U3: 'sin_pago'}  # the PUE invoice is not tracked
    assert out['pagos_ajenos'] == 1
    assert next(r for r in out['rows'] if r['u'] == U1)['pagado'] == 100.0


def make_certificate(days_before, days_after, rfc, serial=None):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, 'EMPRESA PRUEBA'), x509.NameAttribute(NameOID.SERIAL_NUMBER, rfc)]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(serial or x509.random_serial_number())
        .not_valid_before(now - timedelta(days=days_before))
        .not_valid_after(now + timedelta(days=days_after))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.DER)


def test_certificate_validity_states_and_holder_kind():
    now = datetime.now(timezone.utc)
    assert certificate_info(make_certificate(10, 400, 'ABC010101AB1'), now)['s'] == 'vigente'
    assert certificate_info(make_certificate(10, 10, 'ABC010101AB1'), now)['s'] == 'critico'
    assert certificate_info(make_certificate(10, 60, 'ABC010101AB1'), now)['s'] == 'por_vencer'
    assert certificate_info(make_certificate(400, -5, 'ABC010101AB1'), now)['s'] == 'vencido'
    assert certificate_info(make_certificate(-5, 400, 'ABC010101AB1'), now)['s'] == 'aun_no'
    with pytest.raises(ValueError):
        certificate_info(b'esto no es un certificado', now)
    assert holder_kind('FIEL RL/a.cer') == 'RL'
    assert holder_kind('SELLO DIGITAL/a.cer') == 'CSD'
    assert holder_kind('FIEL EMPRESA/a.cer') == 'FIEL'


def test_certificate_index_flags_only_foreign_sello_and_unreadable_files():
    index = CertIndex('ABC010101AB1')
    index.add('SELLO DIGITAL/propio.cer', make_certificate(1, 900, 'ABC010101AB1'))
    index.add('SELLO DIGITAL/ajeno.cer', make_certificate(1, 900, 'ZZZ010101ZZ9'))
    index.add('FIEL REPRESENTANTE/persona.cer', make_certificate(1, 900, 'ZZZ010101ZZ9'))  # a person's FIEL is allowed
    index.add('SELLO DIGITAL/roto.cer', b'basura')
    out = index.result()
    by_name = {r['p'].split('/')[-1]: r for r in out['rows']}
    assert by_name['propio.cer']['why'] == '' and by_name['propio.cer']['emp']
    assert by_name['ajeno.cer']['why'] == 'rfc_ajeno'
    assert by_name['persona.cer']['why'] == '' and not by_name['persona.cer']['emp']
    assert by_name['roto.cer']['s'] == 'ilegible' and out['revisar'] == 2


def test_certificate_status_boundaries():
    from app.cert_groups import certificate_status

    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert certificate_status(now + timedelta(days=90), now) == ('por_vencer', 90)
    assert certificate_status(now + timedelta(days=90, seconds=1), now) == ('por_vencer', 90)  # floor: still 90 days
    assert certificate_status(now + timedelta(days=91), now)[0] == 'vigente'
    assert certificate_status(now + timedelta(days=30), now) == ('por_vencer', 30)
    assert certificate_status(now + timedelta(days=30) - timedelta(seconds=1), now) == ('critico', 29)
    assert certificate_status(now + timedelta(days=29, hours=23), now) == ('critico', 29)
    assert certificate_status(now, now)[0] == 'critico'  # the very instant is still valid
    assert certificate_status(now - timedelta(seconds=1), now)[0] == 'vencido'


def test_certificate_index_dedups_by_serial_and_exposes_public_data():
    index = CertIndex('ABC010101AB1')
    cert = make_certificate(1, 400, 'ABC010101AB1', serial=int('30303030303030303030', 16))
    index.add('FIEL/a.cer', cert)
    index.add('Respaldo/copia.cer', cert)
    index.add('SELLO DIGITAL/otro.cer', make_certificate(1, 60, 'ABC010101AB1'))
    out = index.result()
    assert out['total'] == 2 and out['por_vencer'] == 1
    first = next(r for r in out['rows'] if r['k'] == 'FIEL')
    assert first['serie'] == '0000000000' and first['hasta_ts'].endswith('+00:00')
