"""Plan v1.1, Cambio 1: read compliance documents for the document traffic light, in memory.

Recognized: the SAT compliance opinion (32-D), the IMSS compliance opinion and the Infonavit «Constancia de
situación fiscal… aportaciones patronales y entero de descuentos». The SAT's Constancia de Situación Fiscal is
delegated to csf_extract. These PDFs carry text (no OCR). The original chain is the main source and must agree
with the visible fields; any disagreement, an unknown result or a missing field sends the document to human
review. The digital seal is not verified: everything is «read from the document», never validated before the
SAT, IMSS or Infonavit. Nothing is logged and error messages carry no document data.
"""

import re
from datetime import date, datetime, timedelta

from .csf_extract import CsfError, fold, is_infonavit, read_pdf

RFC = r'[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}'
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
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
    )
}
MAX_BYTES = 10 * 1024 * 1024


class ComplianceError(ValueError):
    """User-facing problem with the file; the message never contains document data."""


def any_date(text):
    """«25 de abril de 2026», «25 de abril 2026», «25/04/2026» or «25-04-2026» → date."""
    t = fold(text or '')
    m = re.search(r'(\d{1,2})\s*DE\s*([A-Z]+)\s*(?:DE(?:L)?\s*)?(\d{4})', t)
    try:
        if m and m.group(2) in MONTHS:
            return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
        m = re.search(r'(\d{2})[/-](\d{2})[/-](\d{4})', t)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        m = re.search(r'(\d{4})[/-](\d{2})[/-](\d{2})', t)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    return None


def kind_of(text):
    f = fold(text)
    if 'CONSTANCIA DE SITUACION FISCAL' in f and is_infonavit(f):
        return 'infonavit'
    if 'SEGURO SOCIAL' in f or 'IMSS' in f:
        if 'OPINION' in f or 'INVOCANTE' in f:
            return 'imss_opinion'
    if 'OPINION' in f and 'CUMPLIMIENTO' in f:
        return 'sat_opinion'
    if 'CONSTANCIA DE SITUACION FISCAL' in f:
        return 'csf'
    return None


def result(kind, authority, fields, read, warnings):
    missing = [k for k in ('rfc', 'folio', 'issued_on', 'result') if not fields.get(k)]
    if missing:
        warnings.append('No se leyeron todos los datos del documento: revísalo y captura lo que falte.')
    return {
        'kind': kind,
        'authority': authority,
        'fields': fields,
        'read': sorted(read),
        'warnings': warnings,
        'review': bool(missing or warnings),
        'authority_validated': False,
    }


def sat_opinion(text):
    fields, read, warnings = {}, set(), []
    compact = re.sub(r'\s+', '', text)
    chain = re.search(r'\|\|(' + RFC + r')\|([A-Z0-9]+)\|(\d{2})-(\d{2})-(\d{4})\|([PN])\|\|(\d+)\|\|', compact)
    f = fold(text)
    visible_result = re.search(r'SENTIDO\s*:?\s*(POSITIVO|NEGATIVO)', f) or re.search(r'\b(POSITIVO|NEGATIVO)\b', f)
    visible_rfc = re.search(r'RFC\s*:?\s*(' + RFC + ')', f)
    visible_folio = re.search(r'FOLIO\s*:?\s*([A-Z0-9]{6,})', f)
    stamp = re.search(r'(\d{1,2})\s*DE\s*([A-Z]+)\s*DE\s*(\d{4})\s*A\s*LAS\s*(\d{1,2}):(\d{2})', f)
    visible_date = any_date(stamp.group(0)) if stamp else None
    if chain:
        try:
            fields['issued_on'] = date(int(chain.group(5)), int(chain.group(4)), int(chain.group(3)))
        except ValueError:
            fields['issued_on'] = None
        fields.update(rfc=chain.group(1), folio=chain.group(2))
        fields['result'] = 'positive' if chain.group(6) == 'P' else 'negative'
        fields['certificate'] = chain.group(7)
        read |= {'rfc', 'folio', 'issued_on', 'result'}
        checks = [
            (visible_rfc, lambda m: m.group(1) == fields['rfc']),
            (visible_folio, lambda m: m.group(1) == fields['folio']),
            (visible_result, lambda m: (m.group(1) == 'POSITIVO') == (fields['result'] == 'positive')),
        ]
        if any(m is None or not ok(m) for m, ok in checks) or (visible_date and visible_date != fields['issued_on']):
            warnings.append('La cadena original no coincide con los datos visibles del documento.')
    else:
        warnings.append('No se encontró la cadena original: los datos se tomaron del texto visible.')
        if visible_rfc:
            fields['rfc'] = visible_rfc.group(1)
            read.add('rfc')
        if visible_folio:
            fields['folio'] = visible_folio.group(1)
            read.add('folio')
        if visible_result:
            fields['result'] = 'positive' if visible_result.group(1) == 'POSITIVO' else 'negative'
            read.add('result')
        if visible_date:
            fields['issued_on'] = visible_date
            read.add('issued_on')
    if stamp:
        try:
            fields['issued_at'] = (
                datetime(
                    visible_date.year, visible_date.month, visible_date.day, int(stamp.group(4)), int(stamp.group(5))
                ).isoformat()
                if visible_date
                else None
            )
        except ValueError:
            pass
    fields['omissions'] = omissions(text) if fields.get('result') == 'negative' else []
    return result('sat_opinion', 'SAT', fields, read, warnings)


def omissions(text):
    """Omitted obligations of a negative SAT opinion: «<obligation>.» followed by its exercise (year)."""
    m = re.search(r'(?i)cumplimiento\s+de\s+obligaciones', text)
    body = text[m.end() :] if m else text
    end = re.search(r'(?i)cadena\s+original|sello\s+digital', body)
    body = body[: end.start()] if end else body
    found = []
    for item in re.finditer(
        r'((?:Declaraci|Pago|Entero|Ajuste|Informativa)[^\n]{5,200}?\.?)\s*\n?\s*(20\d{2})\b', body
    ):
        name = re.sub(r'\s+', ' ', item.group(1)).strip()
        if name and {'name': name, 'year': int(item.group(2))} not in found:
            found.append({'name': name, 'year': int(item.group(2))})
    return found[:30]


def imss_opinion(text):
    fields, read, warnings = {}, set(), []
    joined = text.replace('\r', '')
    chain_start = re.search(r'(?i)invocante\s*:', joined)
    chain = joined[chain_start.start() :] if chain_start else ''
    flat = re.sub(r'\s*\n\s*', ' ', chain)

    def pair(key, stop=r'\|'):
        m = re.search(key + r'\s*:\s*([^|]*?)\s*(?:' + stop + '|$)', flat, re.I)
        return m.group(1).strip() if m else None

    opinion = pair('Opini[oó]n')
    rfc = pair('RFC')
    folio = pair('Folio')
    issued = any_date(pair('Fecha') or '')
    start = any_date(pair('FechaInicioVigencia') or '')
    end = any_date(pair('FechaFinVigencia') or '')
    f = fold(text)
    visible = re.search(r'SE\s*EMITE\s*OPINION\s*(POSITIVA|NEGATIVA|SIN\s*OPINION)', f)
    workers = re.search(r'REGISTRADO\(S\)\s*(\d+)\s*TRABAJADOR', f)
    mapping = {'POSITIVA': 'positive', 'NEGATIVA': 'negative', 'SIN OPINION': 'no_opinion'}
    if chain:
        if rfc and re.fullmatch(RFC, rfc.replace(' ', '').upper()):
            fields['rfc'] = rfc.replace(' ', '').upper()
            read.add('rfc')
        if folio and re.fullmatch(r'\d{10,30}', folio.replace(' ', '')):
            fields['folio'] = folio.replace(' ', '')
            read.add('folio')
        if opinion:
            fields['result'] = mapping.get(re.sub(r'\s+', ' ', fold(opinion)).strip())
            if fields['result']:
                read.add('result')
        if issued or start:
            fields['issued_on'] = issued or start
            read.add('issued_on')
        if end:
            fields['official_valid_until'] = end
            read.add('official_valid_until')
        if visible and fields.get('result') != mapping.get(re.sub(r'\s+', ' ', visible.group(1))):
            warnings.append('La cadena original no coincide con el sentido visible de la opinión.')
        visible_rfc = re.search(r'CLAVE\s*DE\s*RFC\s*:?\s*(' + RFC + ')', f)
        if visible_rfc and fields.get('rfc') and visible_rfc.group(1) != fields['rfc']:
            warnings.append('El RFC visible no coincide con la cadena original.')
    else:
        warnings.append('No se encontró la cadena original: los datos se tomaron del texto visible.')
        if visible:
            fields['result'] = mapping.get(re.sub(r'\s+', ' ', visible.group(1)))
            read.add('result')
        m = re.search(r'CLAVE\s*DE\s*RFC\s*:?\s*(' + RFC + ')', f)
        if m:
            fields['rfc'] = m.group(1)
            read.add('rfc')
        m = re.search(r'FOLIO\s*:?\s*(\d{10,30})', f)
        if m:
            fields['folio'] = m.group(1)
            read.add('folio')
    if workers:
        fields['workers'] = int(workers.group(1))
        read.add('workers')
    if not fields.get('official_valid_until') and fields.get('issued_on'):
        fields['official_valid_until'] = fields['issued_on']  # Same day, until 23:59:59 (per the document).
    return result('imss_opinion', 'IMSS', fields, read, warnings)


def infonavit(text):
    fields, read, warnings = {}, set(), []
    f = fold(text)
    folio = re.search(r'FOLIO\s*:?\s*(\d+\s*/\s*\d{4})', f)
    rfc = re.search(r'RFC\s*:?\s*(' + RFC + ')', f)
    issued = re.search(r'\bA\s+(\d{1,2}\s*DE\s*[A-Z]+\s*DE\s*\d{4})', f)
    chain = re.search(r'(\d+\s*/\s*\d{4})\s*\|\s*(' + RFC + r')\s*\|', f)
    if folio:
        fields['folio'] = re.sub(r'\s+', '', folio.group(1))
        read.add('folio')
    if rfc:
        fields['rfc'] = rfc.group(1)
        read.add('rfc')
    if issued:
        fields['issued_on'] = any_date(issued.group(1))
        read.add('issued_on')
    if 'SIN ADEUDO' in f and re.search(r'S[I]\s*SE\s*ENCUENTRA\s*AL\s*CORRIENTE', f):
        fields['result'] = 'positive'
        read.add('result')
    elif 'CON ADEUDO' in f or re.search(r'NO\s*SE\s*ENCUENTRA\s*AL\s*CORRIENTE', f):
        fields['result'] = 'negative'
        read.add('result')
        warnings.append('Constancia con adeudo: confirma el resultado (aún no hay un ejemplo real de este caso).')
    workers = re.search(r'CUENTA\s*CON\s*(\d+)\s*TRABAJADOR\(ES\)\s*ACTIVO\(S\)', f)
    if workers:
        fields['workers'] = int(workers.group(1))
        read.add('workers')
    bimester = re.search(r'AL\s*(\d)\s*(?:ER|DO|TO|O)?\.?\s*BIMESTRE\s*DE\s*(\d{4})', f)
    if bimester:
        fields['bimester'] = f'{bimester.group(2)}-B{bimester.group(1)}'
        read.add('bimester')
    if chain:
        if fields.get('folio') != re.sub(r'\s+', '', chain.group(1)) or fields.get('rfc') != chain.group(2):
            warnings.append('La cadena original no coincide con el folio o el RFC visibles.')
    else:
        warnings.append('No se encontró la cadena original del documento.')
    if fields.get('issued_on'):
        fields['official_valid_until'] = fields['issued_on'] + timedelta(days=30)
    return result('infonavit', 'INFONAVIT', fields, read, warnings)


def analyze(data):
    """Proposal from a compliance PDF; raises ComplianceError with a data-free message."""
    if len(data) > MAX_BYTES:
        raise ComplianceError('El archivo supera el límite de 10 MB.')
    try:
        pages = read_pdf(data)
    except CsfError as exc:
        raise ComplianceError(str(exc)) from None
    texts = []
    for p in pages[:5]:
        try:
            texts.append(p.extract_text() or '')
        except Exception:  # noqa: BLE001 - a broken text layer counts as no text; the content is never logged
            texts.append('')
    text = '\n'.join(texts)
    if not text.strip():
        raise ComplianceError('El PDF no tiene texto: carga el documento descargado del portal, no un escaneo.')
    kind = kind_of(text)
    if kind == 'sat_opinion':
        return sat_opinion(text)
    if kind == 'imss_opinion':
        return imss_opinion(text)
    if kind == 'infonavit':
        return infonavit(text)
    if kind == 'csf':
        from .csf_extract import analyze as csf

        try:
            r = csf(data)
        except CsfError as exc:
            raise ComplianceError(str(exc)) from None
        f = r['fields']
        fields = {'rfc': f.get('rfc'), 'issued_on': f.get('csf_issued_on'), 'result': 'positive', 'folio': None}
        out = result('csf', 'CSF', fields, {k for k in ('rfc', 'issued_on') if fields.get(k)}, list(r['warnings']))
        out['review'] = not (fields['rfc'] and fields['issued_on'])
        out['pages'] = r['pages']
        return out
    raise ComplianceError(
        'No se reconoció el documento: carga la opinión del SAT, la del IMSS, la constancia del Infonavit o la CSF.'
    )


def only_pages(data, pages):
    from .csf_extract import csf_pages_pdf

    return csf_pages_pdf(data, pages)
