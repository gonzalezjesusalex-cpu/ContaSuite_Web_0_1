"""Descarga de declaraciones con un navegador visible, adaptada de ContaSuite 0.6 (Declara v0.2.6).

Fase 1: sólo se ejecuta contra la dirección que el administrador del equipo pone en la configuración del agente
(`sat.base_url`), pensada para un SAT simulado. El usuario inicia sesión él mismo en la ventana; el agente nunca
recibe ni guarda FIEL, llaves privadas ni contraseñas. El perfil del navegador guarda sólo cookies de navegación.

La lógica pura (filas, nombres, validación de PDF) está separada del navegador para probarla sin Playwright.
"""

import hashlib
import logging
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


def row_year(cells, columns):
    """Ejercicio de una fila (texto), o '' si la tabla no tiene esa columna."""
    index = columns.get('ejercicio')
    return re.sub(r'\s+', ' ', cells[index]).strip() if index is not None and index < len(cells) else ''


def has_pagination(page):
    for selector in sel.PAGINATION_CONTROLS:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:  # noqa: BLE001 - an unusual selector never stops the dry run
            continue
    return False


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

    `options`: base_url (obligatoria), profile_dir, browsers_dir, headless (sólo pruebas), login_timeout (s),
    guided (entrada guiada al portal), ejercicio (sólo las filas de ese año), dry_run (prueba en seco: reconoce la
    tabla y la describe sin descargar nada).
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
    wanted_year = str(options['ejercicio']) if options.get('ejercicio') else ''
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
            if options.get('guided'):
                guided_entry(page)
            notify({'fase': 'esperando_sesion'})
            consulta = _wait_consulta(context, login_timeout, stop, notify)
            if consulta is None:
                raise SatError('sat_cancelado' if stop() else 'sat_sin_consulta')

            rows = consulta.locator('table tbody tr')
            if rows.count() == 0:
                rows = consulta.locator('table tr')
            heads = consulta.locator('table th')
            header_texts = [heads.nth(i).inner_text(timeout=800) for i in range(heads.count())]
            columns = column_map(header_texts)
            entries = []
            for i in range(min(rows.count(), MAX_ROWS)):
                row = rows.nth(i)
                cells = row.locator('td')
                if cells.count() < 2:
                    continue
                texts = [cells.nth(j).inner_text(timeout=800) for j in range(cells.count())]
                parsed = row_entry(texts, columns)
                year = row_year(texts, columns)
                # With a fiscal year requested, only its rows; a table without that column is not filtered.
                if wanted_year and year and year != wanted_year:
                    continue
                if parsed and find_pdf_control(row) is not None:
                    entries.append((i, *parsed))
            if not entries:
                raise SatError('sat_sin_controles')
            if options.get('dry_run'):
                # First contact with the real portal: say what is recognized, click and download nothing.
                return {
                    'prueba_en_seco': True,
                    'detectadas': len(entries),
                    'guardadas': 0,
                    'fallidas': [],
                    'archivos': [],
                    'encabezados': [norm(h)[:60] for h in header_texts][:20],
                    'columnas': columns,
                    'coincide_url': any(part in (consulta.url or '').lower() for part in sel.CONSULTA_URL_PARTS),
                    'paginacion': has_pagination(consulta),
                }

            notify({'fase': 'descargando', 'total': len(entries), 'hechas': 0})
            limits = (
                int(options.get('download_timeout_ms', sel.DOWNLOAD_TIMEOUT_MS)),
                int(options.get('retries', sel.RETRIES)),
                int(options.get('retry_pause_ms', sel.RETRY_PAUSE_MS)),
            )
            cancelled, interrupted, not_pdf_in_a_row = False, None, 0
            for pos, (index, operation, kind, period) in enumerate(entries, start=1):
                if stop():
                    cancelled = True
                    break
                if consulta.is_closed():
                    raise SatError('sat_navegador_cerrado')
                meta = {'fila': pos, 'operacion': operation, 'tipo': kind, 'periodo': period}
                outcome = _download_row(consulta, index, meta, temp, staging, files, errors, limits)
                not_pdf_in_a_row = not_pdf_in_a_row + 1 if outcome == 'no_es_pdf' else 0
                notify({'fase': 'descargando', 'total': len(entries), 'hechas': pos, 'guardadas': len(files)})
                if not_pdf_in_a_row >= sel.MAX_CONSECUTIVE_NOT_PDF:
                    interrupted = 'sesion_expirada'
                    break
                consulta.wait_for_timeout(sel.ROW_PAUSE_MS)
            return {
                'detectadas': len(entries),
                'guardadas': len(files),
                'fallidas': errors,
                'archivos': files,
                **({'cancelada': True} if cancelled else {}),
                **({'interrumpida': interrupted} if interrupted else {}),
            }
        finally:
            context.close()


def guided_entry(page):
    """Recorrido del original hasta la consulta: pestaña «Declara» y enlace «Pagos provisionales del ISR».

    Devuelve si llegó a pulsar el enlace. Nunca falla ni fuerza URLs: la persona puede seguir a mano.
    """
    tab = (
        lambda: page.get_by_text(sel.GUIDE_TAB_TEXT, exact=True).first,
        lambda: page.locator(
            sel.GUIDE_TAB_CONTROLS, has_text=re.compile(rf'^\s*{sel.GUIDE_TAB_TEXT}\s*$', re.IGNORECASE)
        ).first,
    )
    for find in tab:
        try:
            target = find()
            target.wait_for(state='visible', timeout=sel.GUIDE_WAIT_MS)
            target.click(timeout=sel.GUIDE_WAIT_MS)
            page.wait_for_timeout(700)
            break
        except Exception:  # noqa: BLE001 - the next way of finding the tab, or the person, continues
            continue
    pattern = re.compile(sel.GUIDE_LINK_PATTERN, re.IGNORECASE)
    links = (
        lambda: page.get_by_role('link', name=pattern).first,
        lambda: page.locator('a', has_text=pattern).first,
    )
    for find in links:
        try:
            link = find()
            link.wait_for(state='visible', timeout=sel.GUIDE_WAIT_MS)
            link.click(timeout=sel.GUIDE_WAIT_MS)
            page.wait_for_timeout(1200)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _wait_consulta(context, timeout, stop, notify):
    """La página que muestra la tabla de declaraciones; espera a que el usuario llegue hasta ella."""
    deadline = time.time() + timeout
    last = time.time()
    while time.time() < deadline and not stop():
        if not context.pages:
            raise SatError('sat_navegador_cerrado')
        if time.time() - last >= 10:  # a sign of life while the person signs in
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


def _try_row(page, index, staging, meta, timeout):
    """One attempt. ('ok', archivo) or (motivo, None) for a failure that retrying cannot fix; raises on the rest."""
    rows = page.locator('table tbody tr')
    if rows.count() <= index:
        rows = page.locator('table tr')
    control = find_pdf_control(rows.nth(index))
    if control is None:
        return 'sin_control', None
    control.scroll_into_view_if_needed(timeout=5000)
    with page.expect_download(timeout=timeout) as waiting:
        control.click(timeout=10_000)
    download = waiting.value
    got = Path(download.path())
    if not is_pdf_file(got):
        return 'no_es_pdf', None
    if got.stat().st_size > MAX_PDF_BYTES:
        return 'demasiado_grande', None
    target = unique_path(staging, download.suggested_filename or 'declaracion.pdf')
    shutil.copyfile(got, target)
    return 'ok', {
        'nombre': target.name,
        'sha256': sha256_file(target),
        'bytes': target.stat().st_size,
        'operacion': meta['operacion'],
        'tipo': meta['tipo'],
        'periodo': meta['periodo'],
    }


def _download_row(page, index, meta, temp, staging, files, errors, limits):
    """Download one row, retrying network or timing failures. Records a failure with its row and attempts.

    Returns 'ok' or the reason, so the caller can notice an expired session (several files that are not PDF).
    """
    timeout, retries, pause = limits
    attempts = 0
    while True:
        attempts += 1
        try:
            motivo, archivo = _try_row(page, index, staging, meta, timeout)
        except Exception:  # noqa: BLE001 - a failed attempt is retried, then recorded; the queue continues
            if attempts <= retries and not page.is_closed():
                page.wait_for_timeout(pause)
                continue
            motivo, archivo = 'descarga_fallida', None
        if archivo is not None:
            files.append(archivo)
            return 'ok'
        logging.warning('Descarga SAT: fila %s sin PDF (%s, %s intento(s)).', meta['fila'], motivo, attempts)
        errors.append({**meta, 'motivo': motivo, 'intentos': attempts})
        return motivo
