"""In-memory reader of the Excel «Control de obligaciones» (preview only).

One sheet per month; row 1 holds the headers; every following row is a company by NAME (the workbook has no RFC).
Hidden sheets are listed as ignored and never read. Formulas are never evaluated (their cell is left empty and
counted), nothing is written anywhere and the file is not kept: the bytes live only for this call.
"""

from io import BytesIO
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from .company_xlsx import InvalidWorkbook
from .fiscal_import import resolve_header, sheet_period

MAX_BYTES = 15 * 1024 * 1024
MAX_SHEETS = 150
MAX_COLUMNS = 60
MAX_ROWS_PER_SHEET = 3000
MAX_ROWS_TOTAL = 40000
BLANK_PREFIX = '(sin encabezado '


def _check_archive(payload):
    try:
        with ZipFile(BytesIO(payload)) as archive:
            infos = archive.infolist()
            if len(infos) > 400:
                raise InvalidWorkbook('archive_limit')
            for info in infos:
                name = info.filename.lower()
                if info.flag_bits & 1 or '..' in name.split('/') or name.startswith(('/', '\\')):
                    raise InvalidWorkbook()
                if any(s in name for s in ('vbaproject', 'embeddings/', 'externallinks/', 'activex/')):
                    raise InvalidWorkbook('active_content')
                if info.file_size > 40 * 1024 * 1024 or info.file_size / max(info.compress_size, 1) > 300:
                    raise InvalidWorkbook('archive_limit')
    except BadZipFile:
        raise InvalidWorkbook() from None


def read_workbook(payload):
    """Visible sheets as `{name, period, rows}` plus ignored (hidden) sheets and unknown columns, all in memory."""
    if not payload or len(payload) > MAX_BYTES:
        raise InvalidWorkbook('file_size')
    _check_archive(payload)
    try:
        book = load_workbook(BytesIO(payload), read_only=True, data_only=False, keep_links=False)
    except Exception:  # noqa: BLE001 - any parser failure is an invalid file for the user
        raise InvalidWorkbook() from None
    if len(book.worksheets) > MAX_SHEETS:
        raise InvalidWorkbook('sheet_limit')
    sheets, ignored, unknown, formulas, total = [], [], {}, 0, 0
    for ws in book.worksheets:
        if ws.sheet_state != 'visible':
            ignored.append(dict(name=ws.title, reason='hidden'))
            continue
        if ws.max_column and ws.max_column > MAX_COLUMNS:
            raise InvalidWorkbook('column_limit')
        iterator = ws.iter_rows(values_only=True)
        head = next(iterator, None)
        if not head:
            ignored.append(dict(name=ws.title, reason='empty'))
            continue
        headers = []
        for index, value in enumerate(head, 1):
            text = ' '.join(str(value).split()) if value is not None else ''
            headers.append(text or f'{BLANK_PREFIX}{get_column_letter(index)})')
        name_column = next((i for i, h in enumerate(headers) if resolve_header(h)['role'] == 'company'), None)
        for header in headers:
            meaning = resolve_header(header)
            if meaning['role'] == 'unknown':
                unknown.setdefault(header, dict(header=header, reason=meaning['reason'], sheets=[]))['sheets'].append(
                    ws.title
                )
        rows = []
        for number, values in enumerate(iterator, 2):
            total += 1
            if total > MAX_ROWS_TOTAL or number > MAX_ROWS_PER_SHEET:
                raise InvalidWorkbook('row_limit')
            cells = {}
            for header, value in zip(headers, values):
                if isinstance(value, str) and value.startswith('='):
                    formulas += 1
                    value = None
                elif isinstance(value, str):
                    value = value.strip() or None
                if (
                    value is not None
                    and not isinstance(value, (str, int, float, bool))
                    and not hasattr(value, 'isoformat')
                ):
                    raise InvalidWorkbook('invalid_cells')
                cells[header] = value
            name = cells.get(headers[name_column]) if name_column is not None else None
            if name is None or not str(name).strip():
                continue
            rows.append(dict(number=number, name=str(name).strip(), cells=cells))
        sheets.append(dict(name=ws.title, period=sheet_period(ws.title), rows=rows))
    book.close()
    return dict(
        sheets=sheets,
        ignored=ignored,
        unknown_columns=list(unknown.values()),
        formula_cells_omitted=formulas,
    )
