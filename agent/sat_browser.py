"""Descarga de declaraciones con un navegador visible, adaptada de ContaSuite 0.6 (Declara v0.2.6).

Fase 1: sólo se ejecuta contra la dirección que el administrador del equipo pone en la configuración del agente
(`sat.base_url`), pensada para un SAT simulado. El usuario inicia sesión él mismo en la ventana; el agente nunca
recibe ni guarda FIEL, llaves privadas ni contraseñas. El perfil del navegador guarda sólo cookies de navegación.

La lógica pura (filas, nombres, validación de PDF) está separada del navegador para probarla sin Playwright.
"""

import hashlib
import re
import shutil
import tempfile
import time
import unicodedata
from pathlib import Path

import sat_selectors as sel

MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_ROWS = 1000


class SatError(Exception):
    """Fallo con un código estable (sin datos del usuario) para mostrarlo en la interfaz."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def norm(text):
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', text).strip().upper()


def is_consulta_text(body_text):
    normalized = norm(body_text)
    return all(h in normalized for h in sel.CONSULTA_HEADERS)


def column_map(header_cells):
    """Índice de cada columna por su encabezado; las que no aparecen usan el índice del original."""
    found = {}
    heads = [norm(c) for c in header_cells]
    for key, names in sel.COLUMNS.items():
        for i, head in enumerate(heads):
            if any(name in head for name in names):
                found[key] = i
                break
    for key, index in sel.FALLBACK_INDEX.items():
        found.setdefault(key, index)
    return found


def row_entry(cells, columns):
    """(operación, tipo, periodo) de una fila de texto, o None si no parece una fila de declaración."""
    cells = [re.sub(r'\s+', ' ', c).strip() for c in cells]
    operation = next((c for c in cells if re.fullmatch(r'\d{8,}', c.replace(' ', ''))), '')
    if len(cells) < 2:
        return None
    pick = lambda key: cells[columns[key]] if key in columns and columns[key] < len(cells) else ''  # noqa: E731
    return operation, pick('tipo'), pick('periodo')


def is_pdf_file(path):
    try:
        with Path(path).open('rb') as handle:
            return handle.read(5) == b'%PDF-'
    except OSError:
        return False


def unique_path(folder, filename):
    name = Path(filename).name or 'declaracion.pdf'
    if Path(name).suffix.lower() != '.pdf':
        name += '.pdf'
    target = Path(folder) / name
    n = 2
    while target.exists():
        target = Path(folder) / f'{Path(name).stem} ({n}){Path(name).suffix}'
        n += 1
    return target


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def find_pdf_control(row):
    for selector in sel.PDF_CONTROLS:
        found = row.locator(selector)
        if found.count() > 0:
            return found.first
    controls = row.locator('td').first.locator(sel.FIRST_CELL_CONTROLS)
    return controls.first if controls.count() > 0 else None


def download_all(options, staging, on_progress=None, should_stop=None):
    """Abre el navegador, espera a que el usuario llegue a la consulta y descarga cada PDF en `staging`.

    `options`: base_url (obligatoria), profile_dir, browsers_dir, headless (sólo pruebas), login_timeout (s).
    Devuelve {'detectadas', 'guardadas', 'fallidas': [{'fila', 'motivo'}], 'archivos': [...]}.
    Nunca hace clics a ciegas: si no identifica ningún control PDF, termina con `sat_sin_controles`.
    """
    notify = on_progress or (lambda event: None)
    stop = should_stop or (lambda: False)
    base_url = options.get('base_url')
    if not base_url:
        raise SatError('sat_no_habilitado')
    browsers_dir = options.get('browsers_dir')
    if browsers_dir:
        import os

        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(browsers_dir)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SatError('sat_sin_playwright') from None

    staging = Path(staging)
    staging.mkdir(parents=True, exist_ok=True)
    profile = Path(options.get('profile_dir') or (staging.parent / 'sat-profile'))
    profile.mkdir(parents=True, exist_ok=True)
    login_timeout = float(options.get('login_timeout', 600))
    files, errors = [], []
    with sync_playwright() as p, tempfile.TemporaryDirectory(prefix='contasuite_sat_') as temp:
        notify({'fase': 'abriendo'})
        try:
            context = p.firefox.launch_persistent_context(
                str(profile),
                headless=bool(options.get('headless', False)),
                accept_downloads=True,
                downloads_path=temp,
                firefox_user_prefs={
                    'pdfjs.disabled': True,
                    'browser.download.useDownloadDir': True,
                    'browser.download.folderList': 2,
                    'browser.download.dir': temp,
                    'browser.helperApps.neverAsk.saveToDisk': 'application/pdf,application/octet-stream',
                },
            )
        except Exception:  # noqa: BLE001 - Firefox missing or profile locked: one stable code
            raise SatError('sat_navegador_no_disponible') from None
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(base_url, wait_until='domcontentloaded', timeout=90_000)
            notify({'fase': 'esperando_sesion'})
            consulta = _wait_consulta(context, login_timeout, stop, notify)
            if consulta is None:
                raise SatError('sat_cancelado' if stop() else 'sat_sin_consulta')

            rows = consulta.locator('table tbody tr')
            if rows.count() == 0:
                rows = consulta.locator('table tr')
            heads = consulta.locator('table th')
            columns = column_map([heads.nth(i).inner_text(timeout=800) for i in range(heads.count())])
            entries = []
            for i in range(min(rows.count(), MAX_ROWS)):
                row = rows.nth(i)
                cells = row.locator('td')
                if cells.count() < 2:
                    continue
                parsed = row_entry([cells.nth(j).inner_text(timeout=800) for j in range(cells.count())], columns)
                if parsed and find_pdf_control(row) is not None:
                    entries.append((i, *parsed))
            if not entries:
                raise SatError('sat_sin_controles')

            notify({'fase': 'descargando', 'total': len(entries), 'hechas': 0})
            for pos, (index, operation, kind, period) in enumerate(entries, start=1):
                if stop():
                    errors.append({'fila': pos, 'motivo': 'cancelado'})
                    break
                _download_row(consulta, index, pos, (operation, kind, period), temp, staging, files, errors)
                notify({'fase': 'descargando', 'total': len(entries), 'hechas': pos, 'guardadas': len(files)})
                consulta.wait_for_timeout(sel.ROW_PAUSE_MS)
            return {'detectadas': len(entries), 'guardadas': len(files), 'fallidas': errors, 'archivos': files}
        finally:
            context.close()


def _wait_consulta(context, timeout, stop, notify):
    """La página que muestra la tabla de declaraciones; espera a que el usuario llegue hasta ella."""
    deadline = time.time() + timeout
    last = time.time()
    while time.time() < deadline and not stop():
        if time.time() - last >= 30:  # a sign of life while the person signs in
            notify({'fase': 'esperando_sesion'})
            last = time.time()
        for candidate in reversed(context.pages):
            try:
                url = (candidate.url or '').lower()
                if any(part in url for part in sel.CONSULTA_URL_PARTS) and candidate.locator('table').count() > 0:
                    return candidate
                if is_consulta_text(candidate.locator('body').inner_text(timeout=800)):
                    return candidate
            except Exception:  # noqa: BLE001 - a page that is navigating is looked at again on the next turn
                continue
        time.sleep(0.5)
    return None


def _download_row(page, index, pos, meta, temp, staging, files, errors):
    operation, kind, period = meta
    try:
        rows = page.locator('table tbody tr')
        if rows.count() <= index:
            rows = page.locator('table tr')
        control = find_pdf_control(rows.nth(index))
        if control is None:
            errors.append({'fila': pos, 'motivo': 'sin_control'})
            return
        control.scroll_into_view_if_needed(timeout=5000)
        with page.expect_download(timeout=sel.DOWNLOAD_TIMEOUT_MS) as waiting:
            control.click(timeout=10_000)
        download = waiting.value
        got = Path(download.path())
        if not is_pdf_file(got):
            errors.append({'fila': pos, 'motivo': 'no_es_pdf'})
            return
        if got.stat().st_size > MAX_PDF_BYTES:
            errors.append({'fila': pos, 'motivo': 'demasiado_grande'})
            return
        target = unique_path(staging, download.suggested_filename or 'declaracion.pdf')
        shutil.copyfile(got, target)
        files.append(
            {
                'nombre': target.name,
                'sha256': sha256_file(target),
                'bytes': target.stat().st_size,
                'operacion': operation,
                'tipo': kind,
                'periodo': period,
            }
        )
    except Exception:  # noqa: BLE001 - one failed row is recorded and the queue continues
        errors.append({'fila': pos, 'motivo': 'descarga_fallida'})
