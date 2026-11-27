"""Motor de Declara tras el rediseño (sección 3) y paridad de nombres con el escritorio (sección 6, puntos 1 a 6)."""

import importlib.util
import io
import sys
import types
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from app import declara_engine as motor
from app import declara_rules as rules

ROOT = Path(__file__).resolve().parents[2]
RFC = 'ASU260331IWA'


def load_extractor():
    spec = importlib.util.spec_from_file_location('extract_declara_engine', ROOT / 'scripts/extract_declara_engine.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def original():
    """El motor de escritorio sin parches, cargado como módulo propio."""
    module = types.ModuleType('declara_original')
    sys.modules[module.__name__] = module
    exec(compile(load_extractor().extract(patched=False), 'declara_original', 'exec'), module.__dict__)
    yield module
    sys.modules.pop(module.__name__, None)


def pdf(kind='DECLARACION', dtype='Normal', month='Octubre', year='2026', rfc=RFC, operation='100', extra=''):
    stream = io.BytesIO()
    c = canvas.Canvas(stream, invariant=1)
    lines = [
        'DECLARACION PROVISIONAL O DEFINITIVA DE IMPUESTOS FEDERALES',
        f'RFC: {rfc}',
        'Denominación o razón social: ARKOS SUMINISTROS',
        f'Tipo de declaración: {dtype}',
        f'Período de la declaración: {month}',
        f'Ejercicio: {year}',
        f'Número de operación: {operation}',
    ]
    if kind == 'ACUSE':
        lines.insert(0, 'ACUSE DE RECIBO')
    if extra:
        lines.append(extra)
    for n, line in enumerate(lines):
        c.drawString(40, 800 - n * 25, line)
    c.save()
    return stream.getvalue()


def image_pdf():
    stream = io.BytesIO()
    c = canvas.Canvas(stream, invariant=1)
    c.rect(40, 40, 200, 200, fill=1)
    c.save()
    return stream.getvalue()


def plan(infos):
    return {i.path.name: (i.status, i.expected_name) for i in infos}


def write(folder, files):
    for name, data in files.items():
        (folder / name).write_bytes(data)


# ---------------------------------------------------------------- paridad y nombres (punto 1)


def test_extracted_engine_is_original_plus_approved_patches():
    import ast

    extractor = load_extractor()
    source = (ROOT / 'reference/desktop/Declara/organizador_sat_v26.py').read_text(encoding='utf-8-sig')
    extracted = ast.parse((ROOT / 'backend/app/declara_engine.py').read_text(encoding='utf-8'))
    old = {n.name: n for n in ast.parse(source).body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    seen = set()
    for node in extracted.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in old:
            expected = ast.parse(extractor.apply_patches(node.name, extractor.node_source(source, old[node.name])))
            assert ast.dump(node) == ast.dump(expected.body[0]), node.name
            seen.add(node.name)
    assert set(extractor.PATCHES) <= seen
    assert extractor.extract() == (ROOT / 'backend/app/declara_engine.py').read_text(encoding='utf-8')


def test_names_identical_to_desktop(tmp_path, original):
    write(
        tmp_path,
        {
            'decl.pdf': pdf(),
            'acuse.pdf': pdf('ACUSE'),
            'complementaria.pdf': pdf(dtype='Complementaria', operation='200'),
            'otra complementaria.pdf': pdf(dtype='Complementaria', operation='201'),
            'acuse compl.pdf': pdf('ACUSE', 'Complementaria', operation='202'),
            'COMPL 2.pdf': pdf(dtype='Complementaria', operation='203'),
            'resico.pdf': pdf(month='Mayo', extra='REGIMEN SIMPLIFICADO DE CONFIANZA', operation='300'),
            'ACUSE MAYO SALARIOS.pdf': b'sin texto; respaldo por nombre',
            'mayo.pdf': pdf(month='Mayo', operation='301'),
            'segunda decl.pdf': pdf(operation='101'),
            '9.- DECLARACION ISR E IVA SEPTIEMBRE ARKOS.pdf': pdf(month='Septiembre', operation='400'),
            'sept.pdf': pdf(month='Septiembre', operation='401'),
        },
    )
    patched = plan(motor.analyze_folder(tmp_path, 'ARKOS'))
    assert patched == plan(original.analyze_folder(tmp_path, 'ARKOS'))
    assert patched['decl.pdf'][1] == '10.- DECLARACION ISR E IVA OCTUBRE ARKOS.pdf'
    assert patched['segunda decl.pdf'][1] == '10.0.1.- DECLARACION ISR E IVA OCTUBRE ARKOS.pdf'
    assert patched['acuse.pdf'][1] == '10.2.- ACUSE ISR E IVA OCTUBRE ARKOS.pdf'
    assert patched['acuse compl.pdf'][1] == '10.3.- ACUSE COMPLEMENTARIA ISR E IVA OCTUBRE ARKOS.pdf'
    assert patched['COMPL 2.pdf'][1] == '10.1.- DECLARACION COMPLEMENTARIA ISR E IVA OCTUBRE ARKOS 2.pdf'
    assert patched['resico.pdf'][1] == '5.1.- DECLARACION ISR E IVA MAYO ARKOS RESICO.pdf'
    assert patched['ACUSE MAYO SALARIOS.pdf'][1] == '5.2.- ACUSE MAYO SALARIOS.pdf'
    assert patched['9.- DECLARACION ISR E IVA SEPTIEMBRE ARKOS.pdf'][0] == 'CORRECTO'
    assert patched['sept.pdf'][1] == '9.0.1.- DECLARACION ISR E IVA SEPTIEMBRE ARKOS.pdf'
    # Las dos complementarias sin consecutivo explícito chocan y el resolvedor les da sub-consecutivo.
    complementary = {patched['complementaria.pdf'][1], patched['otra complementaria.pdf'][1]}
    assert complementary == {
        '10.1.- DECLARACION COMPLEMENTARIA ISR E IVA OCTUBRE ARKOS.pdf',
        '10.1.1.- DECLARACION COMPLEMENTARIA ISR E IVA OCTUBRE ARKOS.pdf',
    }


def test_existing_target_outside_plan_gets_consecutive(tmp_path, original):
    write(tmp_path, {'decl.pdf': pdf(), '10.- DECLARACION ISR E IVA OCTUBRE ARKOS.pdf': image_pdf()})
    assert plan(motor.analyze_folder(tmp_path, 'ARKOS')) == plan(original.analyze_folder(tmp_path, 'ARKOS'))
    assert plan(motor.analyze_folder(tmp_path, 'ARKOS'))['decl.pdf'][1].startswith('10.0.1.-')


# ---------------------------------------------------------------- huella (punto 2)


def test_identical_copies_by_fingerprint(tmp_path):
    same = pdf()
    write(
        tmp_path,
        {
            'a.pdf': same,
            'copia de a.pdf': same,
            'b.pdf': pdf(operation='101'),  # mismo documento, huella distinta: consecutivo de siempre
            '10.2.- ACUSE ISR E IVA OCTUBRE ARKOS.pdf': pdf('ACUSE'),
        },
    )
    (tmp_path / 'acuse bajado otra vez.pdf').write_bytes(
        (tmp_path / '10.2.- ACUSE ISR E IVA OCTUBRE ARKOS.pdf').read_bytes()
    )
    infos = {i.path.name: i for i in motor.analyze_folder(tmp_path, 'ARKOS')}
    copy = infos['copia de a.pdf']
    assert copy.status == rules.COPIA and copy.detail == 'Igual a a.pdf' and copy.identical_to == 'a.pdf'
    assert infos['a.pdf'].expected_name == '10.- DECLARACION ISR E IVA OCTUBRE ARKOS.pdf'
    assert infos['b.pdf'].expected_name == '10.0.1.- DECLARACION ISR E IVA OCTUBRE ARKOS.pdf'
    # El que ya tiene el nombre estándar es el original; la otra descarga es la copia.
    assert infos['10.2.- ACUSE ISR E IVA OCTUBRE ARKOS.pdf'].status == 'CORRECTO'
    assert infos['acuse bajado otra vez.pdf'].status == rules.COPIA
    assert all(len(i.sha256) == 64 for i in infos.values())
    # Las copias idénticas no se renombran ni cuentan dos veces.
    assert copy not in [i for i in infos.values() if i.status == 'RENOMBRAR']
    assert not rules.counts(copy)


# ---------------------------------------------------------------- consecutivo de complementaria (punto 3)


@pytest.mark.parametrize(
    ('filename', 'sequence'),
    [
        ('complementaria marzo 2025.pdf', None),
        ('COMPLEMENTARIA 2026.pdf', None),
        ('complementaria (1999).pdf', None),
        ('complementaria [2024].pdf', None),
        ('COMPL 2.pdf', '2'),
        ('complementaria (3).pdf', '3'),
        ('declaracion compl_12.pdf', '12'),
        ('3.1.- DECLARACION COMPLEMENTARIA ISR E IVA MARZO ARKOS 2.pdf', '2'),
    ],
)
def test_complementary_sequence_never_takes_the_year(tmp_path, filename, sequence):
    path = tmp_path / filename
    path.write_bytes(pdf(dtype='Complementaria', month='Marzo'))
    info = motor.parse_pdf(path, 'ARKOS')
    assert info.complement_sequence == sequence
    extra = f' {sequence}' if sequence else ''
    assert info.expected_name == f'3.1.- DECLARACION COMPLEMENTARIA ISR E IVA MARZO ARKOS{extra}.pdf'
    if filename.startswith('3.1.-'):
        assert info.status == 'CORRECTO'


# ---------------------------------------------------------------- PDF escaneado y RFC de la empresa


def test_scanned_pdf_asks_for_manual_classification(tmp_path):
    (tmp_path / 'escaneo.pdf').write_bytes(image_pdf())
    info = motor.analyze_folder(tmp_path, 'ARKOS')[0]
    assert info.status == 'OMITIDO'
    assert info.detail == 'El PDF es una imagen, sin texto: clasifícalo manualmente.'


def test_rfc_is_checked_against_the_company(tmp_path):
    write(tmp_path, {'a.pdf': pdf(), 'b.pdf': pdf('ACUSE'), 'c.pdf': pdf(rfc='ABC010101AA1', operation='9')})
    by_majority = {i.path.name: i.status for i in motor.analyze_folder(tmp_path, 'ARKOS')}
    assert by_majority == {'a.pdf': 'RENOMBRAR', 'b.pdf': 'RENOMBRAR', 'c.pdf': 'RFC DIFERENTE'}
    infos = motor.analyze_folder(tmp_path, 'ARKOS', expected_rfc='abc010101aa1')
    statuses = {i.path.name: i.status for i in infos}
    assert statuses == {'a.pdf': 'RFC DIFERENTE', 'b.pdf': 'RFC DIFERENTE', 'c.pdf': 'RENOMBRAR'}
    assert 'RFC de la empresa es ABC010101AA1' in infos[0].detail


# ---------------------------------------------------------------- estados de mes (punto 4)


def doc(month, kind='DECLARACION', dtype='Normal', year='2026', **kw):
    return motor.PdfInfo(
        Path(f'{month}-{kind}-{dtype}.pdf'),
        rfc=RFC,
        month=month,
        year=year,
        document_kind=kind,
        declaration_type=dtype,
        status='RENOMBRAR',
        **kw,
    )


def test_month_states():
    infos = [
        doc('OCTUBRE'),
        doc('SEPTIEMBRE'),
        doc('SEPTIEMBRE', 'ACUSE'),
        doc('SEPTIEMBRE', dtype='Complementaria'),
        doc('SEPTIEMBRE', is_resico=True),
        doc('AGOSTO', dtype='Complementaria'),
        doc('AGOSTO', 'ACUSE', dtype='Complementaria'),
    ]
    months = rules.compute_month_status(infos, 2026, today=date(2026, 11, 10))
    assert months['SEPTIEMBRE']['estado'] == rules.COMPLETO and months['SEPTIEMBRE']['falta'] == []
    assert months['SEPTIEMBRE']['complementarias'] == 1 and months['SEPTIEMBRE']['resico'] == 1
    assert months['OCTUBRE']['estado'] == rules.POR_VENCER and months['OCTUBRE']['falta'] == ['Acuse normal']
    assert months['OCTUBRE']['vence'] == '2026-11-17' and months['OCTUBRE']['exigible']
    assert months['AGOSTO']['estado'] == rules.VENCIDO  # las complementarias no completan el mes
    assert months['NOVIEMBRE']['estado'] == rules.EN_CURSO and not months['NOVIEMBRE']['exigible']
    assert months['DICIEMBRE']['estado'] == rules.FUTURO and months['DICIEMBRE']['vence'] == '2027-01-17'
    for day, state in ((1, rules.POR_VENCER), (17, rules.POR_VENCER), (18, rules.VENCIDO), (30, rules.VENCIDO)):
        assert rules.compute_month_status(infos, 2026, today=date(2026, 11, day))['OCTUBRE']['estado'] == state
    later = rules.compute_month_status(infos, 2026, today=date(2026, 11, 18), due_day=20)
    assert later['OCTUBRE']['estado'] == rules.POR_VENCER and later['OCTUBRE']['vence'] == '2026-11-20'


def test_selected_year_without_pdfs_and_ignored_statuses():
    infos = [doc('ENERO'), doc('ENERO', 'ACUSE')]
    past = rules.compute_month_status(infos, 2025, today=date(2026, 11, 10))
    assert len(past) == 12 and {m['estado'] for m in past.values()} == {rules.VENCIDO}
    assert rules.compute_month_status(infos, 2026, today=date(2026, 11, 10))['ENERO']['estado'] == rules.COMPLETO
    for status in ('OMITIDO', 'ERROR', 'RFC DIFERENTE', rules.COPIA, rules.EXCLUIDO):
        ignored = [infos[0], replace(infos[1], status=status)]
        assert rules.compute_month_status(ignored, 2026, today=date(2026, 11, 10))['ENERO']['estado'] == rules.VENCIDO


def test_start_date_from_constancia_then_rfc():
    assert rules.company_start_date(date(2026, 3, 15), RFC, 2026) == (date(2026, 3, 15), 'Constancia')
    assert rules.company_start_date(None, RFC, 2026) == (date(2026, 3, 31), 'RFC')
    assert rules.company_start_date(None, 'GODE800101AA1', 2026) == (None, None)  # persona física
    start, _ = rules.company_start_date(date(2026, 3, 15), RFC, 2026)
    months = rules.compute_month_status([], 2026, start, today=date(2026, 11, 10))
    assert months['FEBRERO']['estado'] == rules.NO_APLICA_ALTA and months['FEBRERO']['falta'] == []
    assert months['MARZO']['estado'] == rules.VENCIDO
    assert {m['estado'] for m in rules.compute_month_status([], 2025, start, today=date(2026, 11, 10)).values()} == {
        rules.NO_APLICA_ALTA
    }


# ---------------------------------------------------------------- nombre manual (punto 5)


def test_detect_standard():
    found = rules.detect_standard('6.2.- ACUSE ISR E IVA JUNIO NARIJ.pdf')
    assert found['choice'] == 'ACUSE NORMAL' and found['month'] == 'JUNIO'
    assert found['texto'] == "se detectó '6.2.-' = acuse normal de junio"
    assert rules.detect_standard('6.- DECLARACION ISR E IVA JUNIO NARIJ')['choice'] == 'DECLARACION NORMAL'
    assert rules.detect_standard('6.3.1.- ACUSE COMPLEMENTARIA ISR E IVA JUNIO NARIJ')['duplicate']
    assert rules.detect_standard('6.4.- ACUSE ISR E IVA JUNIO NARIJ RESICO')['special'] == ['RESICO']
    assert rules.detect_standard('6.1.- ACUSE ISR E IVA JUNIO NARIJ') is None  # decimal de otro tipo
    assert rules.detect_standard('7.- DECLARACION ISR E IVA JUNIO NARIJ') is None  # número de otro mes
    assert rules.detect_standard('acuse junio') is None


def test_validate_manual_name(tmp_path):
    a, b = motor.PdfInfo(tmp_path / 'a.pdf'), doc('JUNIO', 'ACUSE')
    b.expected_name = '6.2.- ACUSE ISR E IVA JUNIO NARIJ.pdf'
    infos = [a, b]
    assert not rules.validate_manual_name('acuse: junio', a, infos)['ok']
    assert not rules.validate_manual_name('CON', a, infos)['ok']
    assert not rules.validate_manual_name('  ', a, infos)['ok']
    clash = rules.validate_manual_name('6.2.- ACUSE ISR E IVA JUNIO NARIJ', a, infos)
    assert clash['errors'] == ['Otro archivo del plan ya usa ese nombre.']
    existing = rules.validate_manual_name('libre', a, infos, existing={'LIBRE.pdf'})
    assert existing['errors'] == ['Ya existe un archivo con ese nombre en la carpeta.']
    # El nombre actual de un archivo que se renombra en el mismo plan queda libre.
    freed = rules.validate_manual_name(b.path.stem, a, infos, existing={b.path.name})
    assert freed['ok']
    plain = rules.validate_manual_name('acuse junio.pdf', a, infos)
    assert plain['ok'] and plain['name'] == 'acuse junio.pdf' and plain['warnings'] and not plain['standard']
    standard = rules.validate_manual_name('6.2.1.- ACUSE ISR E IVA JUNIO NARIJ', a, infos)
    assert standard['ok'] and not standard['warnings'] and standard['standard']['month'] == 'JUNIO'


def test_manual_name_counts_or_not_in_control(tmp_path):
    decl = doc('JUNIO')
    scanned = motor.PdfInfo(tmp_path / 'escaneo.pdf', status='OMITIDO')
    before = rules.compute_month_status([decl, scanned], 2026, today=date(2026, 11, 10))['JUNIO']['estado']
    assert before == rules.VENCIDO
    rules.apply_manual_name(scanned, 'acuse junio.pdf', count=False)
    assert scanned.status == 'RENOMBRAR' and scanned.manual_override and scanned.origin == 'manual'
    assert rules.compute_month_status([decl, scanned], 2026, today=date(2026, 11, 10))['JUNIO']['estado'] == before
    rules.apply_manual_name(scanned, 'acuse junio.pdf', count=True, choice='ACUSE NORMAL', month='Junio', year='2026')
    assert scanned.year == '2026' and scanned.month == 'JUNIO' and scanned.document_kind == 'ACUSE'
    assert (
        rules.compute_month_status([decl, scanned], 2026, today=date(2026, 11, 10))['JUNIO']['estado'] == rules.COMPLETO
    )


def test_manual_type_with_month(tmp_path):
    scanned = motor.PdfInfo(tmp_path / 'escaneo.pdf', status='OMITIDO')
    name = rules.manual_name_for_month(scanned, 'ACUSE COMPLEMENTARIA', 'junio', [scanned], 'Narij')
    assert name == '6.3.- ACUSE COMPLEMENTARIA ISR E IVA JUNIO NARIJ.pdf'
    assert rules.manual_name_for_month(scanned, 'ACUSE NORMAL', 'Juni', [scanned], 'Narij') is None


# ---------------------------------------------------------------- excluir (punto 6, parte del motor)


def test_excluded_does_not_count_and_reincluded_does():
    infos = [doc('JUNIO'), doc('JUNIO', 'ACUSE')]
    infos[1].status = rules.EXCLUIDO
    assert rules.compute_month_status(infos, 2026, today=date(2026, 11, 10))['JUNIO']['estado'] == rules.VENCIDO
    infos[1].status = 'RENOMBRAR'
    assert rules.compute_month_status(infos, 2026, today=date(2026, 11, 10))['JUNIO']['estado'] == rules.COMPLETO
