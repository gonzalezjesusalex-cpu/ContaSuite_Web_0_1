"""Bounded in-memory XLSX reader with pluggable source adapters; never evaluates formulas."""

from io import BytesIO
from zipfile import ZipFile
from datetime import date, datetime
import re
from openpyxl import load_workbook
from .fiscal_import import normalize, sheet_period, classify


class InvalidWorkbook(Exception):
    MESSAGES = {
        'invalid_file': 'No se pudo leer el XLSX. Comprueba que no esté cifrado ni dañado y vuelve a guardarlo como Libro de Excel (.xlsx).',
        'file_size': 'El archivo debe contener datos y pesar como máximo 8 MB.',
        'archive_limit': 'El XLSX excede los límites de descompresión segura (40 MB en total o 16 MB por componente).',
        'active_content': 'El libro contiene macros, objetos incrustados o vínculos externos de datos no admitidos. Usa una copia sin esos componentes.',
        'external_relationship': 'El libro contiene un vínculo externo no admitido. Sólo se permiten hipervínculos web o de correo; nunca se abren durante el análisis.',
        'sheet_limit': 'El libro supera el máximo de 24 hojas.',
        'column_limit': 'Una hoja declara más de 100 columnas. Usa una copia con sólo la tabla necesaria; el formato de columnas vacías también puede ampliar el rango de Excel.',
        'row_limit': 'El libro excede 10.000 filas recorridas o 3.000 registros de empresas.',
        'missing_headers': 'No se reconoció una tabla. En las primeras 25 filas debe haber encabezados como RFC y Razón social, Empresa o Nombre del contribuyente.',
        'empty_table': 'Se reconocieron encabezados, pero no hay registros con nombre o RFC debajo de ellos.',
        'invalid_cells': 'Excel contiene celdas o tipos de datos que el lector no puede interpretar con seguridad. Revisa las fechas y vuelve a guardar una copia del libro.',
    }

    def __init__(self, code='invalid_file'):
        self.code = code
        super().__init__(self.MESSAGES.get(code, self.MESSAGES['invalid_file']))


HEADERS = {
    'rfc': {'rfc', 'r.f.c.', 'registro federal de contribuyentes'},
    'name': {'empresa', 'contribuyente', 'razon social', 'nombre', 'nombre del contribuyente'},
    'regime': {'regimen', 'regimen fiscal'},
    'responsible': {'responsable', 'contador', 'contadora'},
    'payment': {'pago', 'condicion de pago'},
    'certificate_date': {'vencimiento', 'vigencia', 'fecha de vencimiento', 'vence fiel', 'vence csd'},
}
OBLIGATIONS = {
    'contabilidad': 'Contabilidad',
    'isr': 'ISR',
    'i.s.r.': 'ISR',
    'iva': 'IVA',
    'i.v.a.': 'IVA',
    'retenciones': 'Retenciones',
    'diot': 'DIOT',
    'repse': 'REPSE',
    'impuesto sobre nomina': 'Impuesto sobre Nómina',
    'isn': 'Impuesto sobre Nómina',
    'nomina 1': 'Nómina 1',
    'nomina 2': 'Nómina 2',
    'imss': 'IMSS',
    'emisiones imss': 'Emisiones IMSS',
}
SENSITIVE = re.compile(
    r'contra|password|clave|secreto|token|usuario|correo|email|idse|sipare|infonavit|registro patronal|fiel|csd|e.?firma|fel|contpaqi',
    re.I,
)


def header(value):
    text = normalize(value or '')
    if SENSITIVE.search(text) and text not in HEADERS['certificate_date']:
        return 'sensitive'
    for field, options in HEADERS.items():
        if text in options:
            return field
    return 'obligation:' + OBLIGATIONS[text] if text in OBLIGATIONS else 'ignored'


def safe_text(value, limit):
    if value is None:
        return ''
    if not isinstance(value, (str, int, float)):
        return ''
    value = str(value).strip()
    if len(value) > limit:
        return ''
    return value


def obligations_adapter(value):
    if isinstance(value, str) and normalize(value) in {'con pago', 'sin pago'}:
        return {
            'kind': 'payment',
            'payment': 'with_payment' if normalize(value) == 'con pago' else 'without_payment',
            'original': value,
        }
    data = classify(value)
    if data['kind'] == 'text':
        if re.fullmatch(r'\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}', str(value)):
            try:
                datetime.strptime(str(value), '%d/%m/%Y')
                data['kind'] = 'date_text_unverified'
            except ValueError:
                data = {'kind': 'invalid_date', 'status': 'unreviewed', 'requires_review': True}
        else:
            data['kind'] = 'responsible_or_note'
            data['original'] = safe_text(value, 150)
    return data


ADAPTERS = {'obligations': obligations_adapter, 'fiscal_metadata': lambda v: None}


def read_xlsx(payload, source):
    import warnings

    # Never log parser warnings: they may contain raw cells. Harmless style and
    # presentation-extension warnings become aggregate codes only.
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter('always')
        result = _read_xlsx(payload, source)
    ignored = 0
    for warning in recorded:
        message = str(warning.message)
        if message == "Workbook contains no default style, apply openpyxl's default" or re.fullmatch(
            r'[A-Za-z ]+extension is not supported and will be removed', message
        ):
            ignored += 1
        else:
            raise InvalidWorkbook('invalid_cells')
    result['presentation_warnings_omitted'] = ignored
    return result


def _read_xlsx(payload, source):
    if source not in ADAPTERS:
        raise InvalidWorkbook()
    book = None
    try:
        if not 0 < len(payload) <= 8 * 1024 * 1024:
            raise InvalidWorkbook('file_size')
        with ZipFile(BytesIO(payload)) as archive:
            infos = archive.infolist()
            if len(infos) > 2000 or sum(i.file_size for i in infos) > 40 * 1024 * 1024:
                raise InvalidWorkbook('archive_limit')
            if len({i.filename for i in infos}) != len(infos):
                raise InvalidWorkbook()
            for i in infos:
                name = i.filename.lower()
                if i.flag_bits & 1 or '..' in name.split('/') or name.startswith(('/', '\\')):
                    raise InvalidWorkbook()
                if any(s in name for s in ['vbaproject', 'embeddings/', 'externallinks/', 'activex/']):
                    raise InvalidWorkbook('active_content')
                if i.file_size > 16 * 1024 * 1024 or i.file_size / max(i.compress_size, 1) > 300:
                    raise InvalidWorkbook('archive_limit')
                if name.endswith('.rels'):
                    from defusedxml.ElementTree import fromstring
                    from urllib.parse import urlsplit

                    for relation in fromstring(archive.read(i)):
                        if relation.get('TargetMode', '').lower() != 'external':
                            continue
                        if (
                            relation.get('Type')
                            != 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink'
                            or urlsplit(relation.get('Target', '')).scheme.lower() not in {'https', 'http', 'mailto'}
                        ):
                            raise InvalidWorkbook('external_relationship')
        book = load_workbook(BytesIO(payload), read_only=True, data_only=False, keep_links=False)
        if len(book.worksheets) > 24:
            raise InvalidWorkbook('sheet_limit')
        rows = []
        sheets = []
        scanned = 0
        for sheet_index, ws in enumerate(book.worksheets, 1):
            if ws.max_column and ws.max_column > 100:
                raise InvalidWorkbook('column_limit')
            if ws.max_row and ws.max_row > 10000:
                raise InvalidWorkbook('row_limit')
            mapping = None
            period = sheet_period(ws.title)
            sheet_info = {
                'index': sheet_index,
                'period': period,
                'rows': 0,
                'header_found': False,
                'formula_cells_omitted': 0,
            }
            sheets.append(sheet_info)
            for number, cells in enumerate(ws.iter_rows(max_col=100), 1):
                scanned += 1
                if scanned > 10000:
                    raise InvalidWorkbook('row_limit')
                values = [c.value if c.data_type != 'f' else None for c in cells]
                sheet_info['formula_cells_omitted'] += sum(c.data_type == 'f' for c in cells)
                if mapping is None:
                    if number > 25:
                        break
                    mapped = [header(v) for v in values]
                    if 'name' in mapped or 'rfc' in mapped:
                        mapping = mapped
                        sheet_info['header_found'] = True
                        sheet_info['ambiguous_headers'] = len(
                            [m for m in mapped if m not in ('sensitive', 'ignored')]
                        ) != len(set(m for m in mapped if m not in ('sensitive', 'ignored')))
                    continue
                if not any(v is not None for v in values):
                    continue
                if len(rows) >= 3000:
                    raise InvalidWorkbook('row_limit')
                safe = {
                    'name': '',
                    'rfc': '',
                    'regime': '',
                    'responsible': '',
                    'cells': {},
                    'source': {'sheet_index': sheet_index, 'row': number, 'period': period},
                    'warnings': [],
                }
                if sheet_info['ambiguous_headers']:
                    safe['warnings'].append('ambiguous_headers')
                for field, value, cell in zip(mapping, values, cells):
                    if field in ('sensitive', 'ignored'):
                        continue
                    if cell.data_type == 'f':
                        safe['warnings'].append('formula_omitted')
                        continue
                    if field in ('name', 'rfc', 'regime', 'responsible'):
                        safe[field] = safe_text(value, 220 if field == 'name' else 150 if field != 'rfc' else 20)
                    elif field == 'certificate_date':
                        safe['certificate_date'] = value.isoformat() if isinstance(value, (date, datetime)) else None
                        if value and not isinstance(value, (date, datetime)):
                            safe['warnings'].append('certificate_date_unverified')
                    elif source == 'obligations' and field.startswith('obligation:'):
                        safe['cells'][field.split(':', 1)[1]] = ADAPTERS[source](value)
                    elif field == 'payment':
                        text = normalize(value or '')
                        safe['payment'] = (
                            'with_payment'
                            if text == 'con pago'
                            else 'without_payment'
                            if text == 'sin pago'
                            else 'unreviewed'
                        )
                if safe['name'] or safe['rfc']:
                    rows.append(safe)
                    sheet_info['rows'] += 1
        if not any(s['header_found'] for s in sheets):
            raise InvalidWorkbook('missing_headers')
        if not rows:
            raise InvalidWorkbook('empty_table')
        return {
            'rows': rows,
            'sheets': sheets,
            'limits': {'max_rows': 3000, 'max_sheets': 24, 'max_bytes': 8 * 1024 * 1024},
            'secrets_import_enabled': False,
        }
    except InvalidWorkbook:
        raise
    except Exception:  # noqa: BLE001 - any parser failure becomes InvalidWorkbook (422) for the user
        raise InvalidWorkbook() from None
    finally:
        if book:
            book.close()
