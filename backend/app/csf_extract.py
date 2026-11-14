"""Read a Constancia de Situación Fiscal (CSF) from a PDF, in memory (Bloque 1).

Order: the PDF text layer first (exact; constancias downloaded from the SAT). Only when there is no text, local
OCR (RapidOCR) on the pages of the constancia. A PDF may carry other documents (INE, IMSS…): only the pages of
the constancia are processed and returned; the others are discarded without keeping or logging anything.

Nothing is saved here and no personal or fiscal data is ever logged or put in an error message. The result is a
proposal for the registration form; the user reviews and confirms it. This is not an SAT validation.
"""

import io
import logging
import re
import threading
import unicodedata
from datetime import date

from . import sat_regimes

MAX_BYTES = 15 * 1024 * 1024
MAX_PAGES = 30
MAX_CSF_PAGES = 5
LOW_CONFIDENCE = 0.93
TITLE = 'CONSTANCIA DE SITUACION FISCAL'
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
RFC_RE = re.compile(r'[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}')
CURP_RE = re.compile(r'[A-Z][AEIOUX][A-Z]{2}\d{6}[HMX][A-Z]{2}[B-DF-HJ-NP-TV-Z]{3}[A-Z0-9]\d')

# Labels as printed by the SAT (accents and case ignored). `None` marks a section boundary that ends the previous
# value but is not read itself. Longer labels first so that "NOMBRE DE LA COLONIA" wins over "NOMBRE".
LABELS = [
    ('NOMBRE DEL MUNICIPIO O DEMARCACION TERRITORIAL:', 'tax_municipality'),
    ('NOMBRE DE LA ENTIDAD FEDERATIVA:', 'tax_state'),
    ('FECHA DE ULTIMO CAMBIO DE ESTADO:', 'last_status_change'),
    ('FECHA INICIO DE OPERACIONES:', 'operations_start'),
    ('DENOMINACION/RAZON SOCIAL:', 'legal_name'),
    ('DENOMINACION / RAZON SOCIAL:', 'legal_name'),
    ('DENOMINACION O RAZON SOCIAL:', 'legal_name'),
    ('NOMBRE DE LA LOCALIDAD:', 'tax_locality'),
    ('NOMBRE DE LA COLONIA:', 'tax_neighborhood'),
    ('ESTATUS EN EL PADRON:', 'padron_status'),
    ('NOMBRE DE VIALIDAD:', 'tax_street'),
    ('TIPO DE VIALIDAD:', 'tax_street_type'),
    ('NUMERO EXTERIOR:', 'tax_exterior_number'),
    ('NUMERO INTERIOR:', 'tax_interior_number'),
    ('SEGUNDO APELLIDO:', 'second_surname'),
    ('PRIMER APELLIDO:', 'first_surname'),
    ('NOMBRE COMERCIAL:', 'trade_name'),
    ('REGIMEN CAPITAL:', 'capital_regime'),
    ('CODIGO POSTAL:', 'tax_postal_code'),
    ('ENTRE CALLE:', 'between_1'),
    ('NOMBRE (S):', 'given_names'),
    ('NOMBRE(S):', 'given_names'),
    ('Y CALLE:', 'between_2'),
    ('IDCIF:', 'idcif'),
    ('CURP:', 'curp'),
    ('RFC:', 'rfc'),
    ('LUGAR Y FECHA DE EMISION', 'issued'),
    ('DATOS DE IDENTIFICACION DEL CONTRIBUYENTE', None),
    ('DATOS DE IDENTIFICACION DE LA PERSONA', None),
    ('DATOS DEL DOMICILIO REGISTRADO', None),
    ('ACTIVIDADES ECONOMICAS', None),
    ('REGIMENES:', None),
    ('OBLIGACIONES:', None),
    ('SUS DATOS PERSONALES', None),
    ('CORREO ELECTRONICO:', None),
    ('TEL. FIJO', None),
    ('TEL. MOVIL', None),
    ('CADENA ORIGINAL', None),
    ('SELLO DIGITAL', None),
    ('CEDULA DE IDENTIFICACION FISCAL', None),
    ('NOMBRE, DENOMINACION O RAZON', None),
    ('PAGINA ', None),
]

log = logging.getLogger(__name__)


class CsfError(ValueError):
    """User-facing problem with the file; the message never contains document data."""


def fold(text):
    """Upper case without accents, keeping the length so that positions map back to the original text."""
    out = []
    for ch in text:
        base = unicodedata.normalize('NFD', ch)[0]
        upper = base.upper()
        out.append(upper if len(upper) == 1 else base)
    return ''.join(out)


def spanish_date(text):
    text = fold(text or '')
    m = re.search(r'(\d{1,2})\s*DE\s*([A-Z]+)\s*DE\s*(\d{4})', text)
    try:
        if m and m.group(2) in MONTHS:
            return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
        m = re.search(r'(\d{2})[/-](\d{2})[/-](\d{4})', text)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None
    return None


# ---------------------------------------------------------------- OCR (lazy, optional, one job at a time)

_engine = None
_engine_lock = threading.Lock()
OCR_SLOTS = threading.BoundedSemaphore(1)


def ocr_available():
    import importlib.util

    return importlib.util.find_spec('rapidocr') is not None and importlib.util.find_spec('onnxruntime') is not None


def quiet():
    for name in list(logging.root.manager.loggerDict):
        if name.lower().startswith('rapidocr'):
            logging.getLogger(name).setLevel(logging.WARNING)


def engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            from rapidocr import RapidOCR

            # The engine logs model paths at INFO (nothing from documents); it sets its own logger level when
            # imported, so quiet it before and after building the engine.
            quiet()
            _engine = RapidOCR()
            quiet()
        return _engine


def prepare(image):
    """Scans arrive skewed and noisy: grey, contrast stretched, bounded size (the engine handles small tilts)."""
    from PIL import ImageOps

    image = ImageOps.exif_transpose(image).convert('L')
    image = ImageOps.autocontrast(image, cutoff=1)
    longest = max(image.size)
    if longest > 2400:
        ratio = 2400 / longest
        image = image.resize((int(image.width * ratio), int(image.height * ratio)))
    return image


def ocr_lines(image, crop_top=None):
    import numpy as np

    if crop_top:
        image = image.crop((0, 0, image.width, int(image.height * crop_top)))
    result = engine()(np.asarray(image))
    if not result or not result.txts:
        return []
    return list(zip(result.txts, (float(s) for s in result.scores), strict=True))


def page_image(page):
    from PIL import Image

    best = None
    for item in page.images:
        try:
            img = Image.open(io.BytesIO(item.data))
            img.load()
        except Exception:  # noqa: BLE001 - an unreadable embedded image is skipped, never reported with data
            continue
        if best is None or img.width * img.height > best.width * best.height:
            best = img
    return best


# ---------------------------------------------------------------- parsing


def csf_page_span(texts, start):
    """Pages of the constancia from its first page: «Página [1] de [n]» when printed, else following pages
    that clearly continue it (regimes, obligations, seal)."""
    m = re.search(r'PAGINA\s*\[?\s*1\s*\]?\s*DE\s*\[?\s*(\d)', fold(texts[start] or ''))
    total = min(int(m.group(1)), MAX_CSF_PAGES) if m else 1
    pages = list(range(start, min(start + total, len(texts))))
    if not m:
        for i in range(start + 1, min(start + MAX_CSF_PAGES, len(texts))):
            folded = fold(texts[i] or '')
            if TITLE in folded or not any(k in folded for k in ('REGIMENES', 'OBLIGACIONES', 'CADENA ORIGINAL')):
                break
            pages.append(i)
    return pages


def fields_from_text(text, scores=None):
    """Values between known labels. `scores` gives, per character, the OCR confidence of its line."""
    folded = fold(text)
    hits = []
    for label, key in LABELS:
        for m in re.finditer(re.escape(label).replace(r'\ ', r'\s*'), folded):
            if not any(m.start() < e and s < m.end() for s, e, _ in hits):
                hits.append((m.start(), m.end(), key))
    hits.sort()
    values = {}
    for i, (_, end, key) in enumerate(hits):
        if key is None or key in values:
            continue
        stop = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        value = re.sub(r'\s+', ' ', text[end:stop]).strip(' :')
        if value:
            conf = min(scores[end:stop]) if scores and end < stop else 1.0
            values[key] = (value, conf)
    return values


def section(text, start_label, end_labels):
    folded = fold(text)
    m = re.search(start_label, folded)
    if not m:
        return ''
    end = len(text)
    for label in end_labels:
        e = re.search(label, folded[m.end() :])
        if e:
            end = min(end, m.end() + e.start())
    return text[m.end() : end]


def regimes_from(text):
    body = section(text, r'REGIMENES\s*:', [r'OBLIGACIONES\s*:', r'SUS DATOS PERSONALES', r'CADENA ORIGINAL'])
    found = []
    for m in re.finditer(r'([A-Za-zÁÉÍÓÚÜÑáéíóúüñ ,.()]{6,}?)\s*(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}/\d{2}/\d{4}))?', body):
        printed = re.sub(r'\s+', ' ', m.group(1)).strip(' ,.')
        if fold(printed).startswith('REGIMEN FECHA') or fold(printed) in {'FECHA INICIO', 'FECHA FIN'}:
            continue
        printed = re.sub(r'(?i)^r[eé]gimen\s+fecha\s+inicio\s+fecha\s+fin\s*', '', printed)
        found.append((printed, spanish_date(m.group(2)), spanish_date(m.group(3)) if m.group(3) else None))
    return found


def obligations_from(text):
    body = section(text, r'OBLIGACIONES\s*:', [r'SUS DATOS PERSONALES', r'CADENA ORIGINAL', r'SELLO DIGITAL'])
    items = []
    for m in re.finditer(r'([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 ,.()/%-]{10,}?)\s*(\d{2}/\d{2}/\d{4})', body):
        description = re.sub(r'\s+', ' ', m.group(1)).strip(' ,.')
        if 'DESCRIPCION DE LA OBLIGACION' in fold(description):
            description = re.sub(r'(?i).*descripci[oó]n de la obligaci[oó]n\s*', '', description)
        if description:
            items.append({'description': description[:300], 'start_date': spanish_date(m.group(2))})
    return items[:50]


def build(values, text, source):
    """Map raw values to the company form, with confidence and notices (no data in the notices' wording)."""
    warnings = []
    low = []

    def take(key, cleaner=lambda v: v):
        if key not in values:
            return None
        raw, conf = values[key]
        cleaned = cleaner(raw)
        if cleaned and conf < LOW_CONFIDENCE:
            low.append(key)
        return cleaned or None

    def first(pattern):
        return lambda v: (pattern.search(fold(v).replace(' ', '')) or [None])[0]

    rfc = take('rfc', first(RFC_RE))
    curp = take('curp', first(CURP_RE))
    idcif = take('idcif', lambda v: (re.search(r'\d{8,11}', v.replace(' ', '')) or [None])[0])
    person_type = 'Moral' if rfc and len(rfc) == 12 else 'Física' if rfc else None
    if person_type == 'Moral':
        name = take('legal_name')
        low = ['name' if k == 'legal_name' else k for k in low]
    else:
        parts = [take(k) for k in ('given_names', 'first_surname', 'second_surname')]
        name = ' '.join(p for p in parts if p) or None
        if {'given_names', 'first_surname', 'second_surname'} & set(low):
            low.append('name')
    municipality, state = take('tax_municipality'), take('tax_state')
    between = ' y '.join(v for v in (take('between_1'), take('between_2')) if v) or None
    status = take('padron_status')
    issued = spanish_date(values.get('issued', ('', 1))[0])
    form = {
        'person_type': person_type,
        'rfc': rfc,
        'idcif': idcif,
        'curp': curp,
        'name': name,
        'trade_name': take('trade_name'),
        'location': ', '.join(v for v in (municipality, state) if v) or None,
        'tax_postal_code': take('tax_postal_code', lambda v: (re.search(r'\d{5}', v) or [None])[0]),
        'tax_street_type': take('tax_street_type'),
        'tax_street': take('tax_street'),
        'tax_exterior_number': take('tax_exterior_number'),
        'tax_interior_number': take('tax_interior_number'),
        'tax_neighborhood': take('tax_neighborhood'),
        'tax_locality': take('tax_locality'),
        'tax_municipality': municipality,
        'tax_state': state,
        'tax_between_streets': between,
        'operations_start': spanish_date(values.get('operations_start', ('', 1))[0]),
        'padron_status': status.upper() if status else None,
        'csf_issued_on': issued,
    }
    # Regimes: only exact catalog matches are proposed; the rest is reported for a manual choice.
    regimes, unmatched = [], []
    for printed, start, end in regimes_from(text):
        code = sat_regimes.match(printed)
        if code:
            regimes.append({'code': code, 'label': sat_regimes.label(code), 'start_date': start, 'end_date': end})
        else:
            unmatched.append(printed)
    current = [r for r in regimes if not r['end_date']]
    form['regimes'] = current or regimes
    form['regime'] = form['regimes'][0]['label'] if form['regimes'] else None
    if unmatched:
        warnings.append('Hay regímenes sin coincidencia en el catálogo: elige el régimen manualmente.')
    if not form['regimes']:
        warnings.append('No se reconoció el régimen fiscal: selecciónalo manualmente.')
    if not rfc:
        warnings.append('No se reconoció el RFC: captúralo manualmente.')
    if not idcif:
        warnings.append('No se reconoció el idCIF: captúralo manualmente.')
    if person_type == 'Física':
        if not curp:
            warnings.append('No se reconoció la CURP: es obligatoria para personas físicas.')
        elif rfc and rfc[:10] != curp[:10]:
            warnings.append('Los primeros 10 caracteres del RFC y de la CURP no coinciden: revisa ambos.')
    if form['padron_status'] and form['padron_status'] != 'ACTIVO':
        warnings.append('El estatus en el padrón no es ACTIVO.')
    if issued and (date.today() - issued).days > 92:
        warnings.append('La constancia tiene más de 3 meses de emitida: conviene descargar una nueva.')
    extras = []
    if 'capital_regime' in values:
        extras.append('Régimen capital: ' + values['capital_regime'][0])
    if 'last_status_change' in values:
        extras.append('Último cambio de estado: ' + values['last_status_change'][0])
    if issued:
        extras.append('Constancia emitida el ' + issued.strftime('%d/%m/%Y'))
    form['notes'] = '; '.join(extras) or None
    return {
        'source': source,
        'fields': {k: v for k, v in form.items() if v not in (None, '', [])},
        'low_confidence': sorted(set(low) & set(form)),
        'warnings': warnings,
        'unmatched_regimes': unmatched,
        'obligations': obligations_from(text),
    }


# ---------------------------------------------------------------- entry point


def read_pdf(data):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    if len(data) > MAX_BYTES:
        raise CsfError('El archivo supera el límite de 15 MB.')
    if not data.startswith(b'%PDF'):
        raise CsfError('Carga la constancia en PDF.')
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise CsfError('El PDF está protegido con contraseña.')
        pages = list(reader.pages)
    except PdfReadError:
        raise CsfError('No se pudo leer el PDF.') from None
    if not pages:
        raise CsfError('El PDF no tiene páginas.')
    if len(pages) > MAX_PAGES:
        raise CsfError('El PDF tiene demasiadas páginas; carga sólo la constancia.')
    return pages


def analyze(data):
    """Proposal for the company form from a CSF PDF. Raises CsfError with a data-free message."""
    pages = read_pdf(data)
    texts = []
    for p in pages:
        try:
            texts.append(p.extract_text() or '')
        except Exception:  # noqa: BLE001 - a broken text layer counts as no text; the content is never logged
            texts.append('')
    start = next((i for i, t in enumerate(texts) if TITLE in fold(t)), None)
    if start is not None:
        span = csf_page_span(texts, start)
        text = '\n'.join(texts[i] for i in span)
        result = build(fields_from_text(text), text, 'text')
        return {**result, 'pages': [i + 1 for i in span], 'page_count': len(pages)}
    if any(t.strip() for t in texts):
        raise CsfError('El documento no contiene «Constancia de Situación Fiscal».')
    if not ocr_available():
        raise CsfError('El PDF es un escaneo y el OCR local no está instalado en este equipo.')
    if not OCR_SLOTS.acquire(timeout=60):
        raise CsfError('Hay otra constancia en análisis. Intenta de nuevo en un momento.')
    try:
        return analyze_scanned(pages)
    finally:
        OCR_SLOTS.release()


def analyze_scanned(pages):
    images = [page_image(p) for p in pages]
    prepared = [prepare(img) if img is not None else None for img in images]
    start = None
    for i, img in enumerate(prepared):
        if img is None:
            continue
        # Cheap pass on the top of each page to find the constancia; other documents are not read further.
        head = fold(' '.join(t for t, _ in ocr_lines(img, crop_top=0.25)))
        if 'CONSTANCIA' in head and 'SITUACION' in head:
            start = i
            break
    if start is None:
        raise CsfError('No se encontró una Constancia de Situación Fiscal en el escaneo.')
    lines_by_page = {start: ocr_lines(prepared[start])}
    texts = [''] * len(pages)
    texts[start] = '\n'.join(t for t, _ in lines_by_page[start])
    # Following pages only while they continue the constancia (regimes, obligations, seal).
    for i in range(start + 1, min(start + MAX_CSF_PAGES, len(pages))):
        if prepared[i] is None:
            break
        lines = ocr_lines(prepared[i])
        folded = fold(' '.join(t for t, _ in lines))
        if TITLE in folded or not any(k in folded for k in ('REGIMENES', 'OBLIGACIONES', 'CADENA ORIGINAL')):
            break
        lines_by_page[i] = lines
        texts[i] = '\n'.join(t for t, _ in lines)
    span = sorted(lines_by_page)
    text, scores = '', []
    for i in span:
        for line, score in lines_by_page[i]:
            text += line + '\n'
            scores.extend([score] * (len(line) + 1))
    result = build(fields_from_text(text, scores), text, 'ocr')
    # Identifiers read by OCR are always marked for review: one wrong character changes the taxpayer.
    result['low_confidence'] = sorted(
        set(result['low_confidence']) | ({'rfc', 'curp', 'idcif'} & set(result['fields']))
    )
    return {**result, 'pages': [i + 1 for i in span], 'page_count': len(pages)}


def csf_pages_pdf(data, pages):
    """A new PDF with only the given 1-based pages (the constancia), for the company file (Bloque 1)."""
    from pypdf import PdfWriter

    reader_pages = read_pdf(data)
    writer = PdfWriter()
    for number in pages:
        if not 1 <= number <= len(reader_pages):
            raise CsfError('Páginas fuera del documento.')
        writer.add_page(reader_pages[number - 1])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
