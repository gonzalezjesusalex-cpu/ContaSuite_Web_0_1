"""Sesión SAT de Declara en modo carpeta (rediseño del 26/11/2026, sección 4.4): cola por fila con guardado y renombrado.

El navegador (Firefox de Playwright, igual que el original) sólo lista las filas de «Consulta de declaraciones» y
descarga una a la vez a una carpeta temporal local. La cola, los filtros (sólo faltantes, periodo), la pausa, los
reintentos y el guardado en la carpeta de la empresa son lógica pura y se prueban sin navegador ni portal real.

Protecciones del original que se conservan: descarga a una carpeta temporal local, encabezado `%PDF-`, una fila a la
vez con 25 s por fila, nada de clics a ciegas (sin icono PDF no se hace clic) y normal y complementaria del mismo mes
se conservan las dos. La FIEL llega en memoria y se entrega a Firefox sin escribirla en disco; con CIEC, el captcha lo
resuelve la persona.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

import declara_folder
import sat_browser as sb
import sat_selectors as sel

MONTHS = ('ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE',
          'NOVIEMBRE', 'DICIEMBRE')  # fmt: skip
ROW_TIMEOUT_MS = sel.DOWNLOAD_TIMEOUT_MS  # 25 s por fila


ROW_KEYS = ('fila', 'operacion', 'tipo', 'periodo', 'ejercicio', 'estado', 'motivo', 'nombre')


def public(rows):
    """Lo que se informa de cada fila: sólo datos de la consulta y su estado, nunca contenido ni controles."""
    return [{k: r[k] for k in ROW_KEYS if k in r and r[k] is not None} for r in rows[:1000]]


class RowError(Exception):
    def __init__(self, motivo):
        super().__init__(motivo)
        self.motivo = motivo


def month_of(period: str) -> str:
    text = sb.norm(period).replace('SETIEMBRE', 'SEPTIEMBRE')
    return next((m for m in MONTHS if m in text), '')


def wanted(row, periodo, ejercicio):
    if periodo and month_of(row.get('periodo', '')) != periodo:
        return False
    return not (ejercicio and row.get('ejercicio') and str(row['ejercicio']) != str(ejercicio))


class Queue:
    """Estado visible de la cola: lo que la web muestra en vivo."""

    def __init__(self, rows, notify):
        self.rows = rows
        self.notify = notify
        self.etapa = 'descargando'

    def counts(self):
        states = [r['estado'] for r in self.rows]
        return {
            'total': len(self.rows),
            'procesadas': sum(s not in {'en_cola', 'descargando'} for s in states),
            'guardadas': sum(s == 'guardado' for s in states),
            'ya_existian': sum(s == 'ya_existia' for s in states),
            'errores': sum(s == 'error' for s in states),
        }

    def report(self):
        return self.notify({'etapa': self.etapa, **self.counts(), 'filas': public(self.rows)}) or {}


def run_queue(rows, download, save, existing_ops, notify, control=None, sleep=time.sleep):
    """Recorre la cola fila por fila. `download(row) -> Path` (temporal local) o RowError/TimeoutError;
    `save(path, row) -> (estado, nombre)`; `control()` devuelve las órdenes de la web (pausar, cancelar, reintentar).
    """
    queue = Queue(rows, notify)
    for row in rows:
        row.setdefault('estado', 'en_cola')
        if row.get('operacion') and row['operacion'] in existing_ops and row['estado'] == 'en_cola':
            row['estado'], row['motivo'] = 'ya_existia', 'Ya está en la carpeta (mismo número de operación).'
    orders = queue.report()
    pending = [r for r in rows if r['estado'] == 'en_cola']
    cancelled = False
    while pending:
        row = pending.pop(0)
        while orders.get('pausar') and not orders.get('cancelar'):
            queue.etapa = 'pausada'
            sleep(1)
            orders = queue.report()
        queue.etapa = 'descargando'
        if orders.get('cancelar'):
            cancelled = True
            break
        row['estado'], row['motivo'] = 'descargando', ''
        queue.report()
        temp = None
        try:
            temp = download(row)
            if not sb.is_pdf_file(temp):
                raise RowError('no_es_pdf')
            row['estado'], row['nombre'] = save(temp, row)
        except TimeoutError:
            row['estado'], row['motivo'] = 'error', 'tiempo_agotado'
        except RowError as error:
            row['estado'], row['motivo'] = 'error', error.motivo
        except declara_folder.FolderError as error:
            row['estado'], row['motivo'] = 'error', error.code
        finally:
            if temp is not None:
                Path(temp).unlink(missing_ok=True)
        orders = queue.report() if control is None else (control() or queue.report())
        for op in orders.get('reintentar') or []:
            again = next((r for r in rows if r.get('operacion') == op and r['estado'] == 'error'), None)
            if again is not None and again not in pending:
                again['estado'], again['motivo'] = 'en_cola', ''
                pending.append(again)
    return {**queue.counts(), 'cancelada': cancelled, 'filas': rows}


# ---------------------------------------------------------------- portal (Playwright)


class Portal:
    """El portal del SAT en el Firefox de Playwright. Sólo lista filas y descarga una a la vez."""

    def __init__(self, options, notify, fiel=None):
        self.options = options
        self.notify = notify
        self.fiel = fiel
        self.temp = Path(tempfile.mkdtemp(prefix='contasuite_sat_'))
        self.playwright = None
        self.context = None
        self.page = None

    def open(self):
        import os

        if self.options.get('browsers_dir'):
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(self.options['browsers_dir'])
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise sb.SatError('sat_sin_playwright') from None
        self.playwright = sync_playwright().start()
        profile = Path(self.options['profile_dir'])
        profile.mkdir(parents=True, exist_ok=True)
        try:
            self.context = self.playwright.firefox.launch_persistent_context(
                str(profile),
                headless=bool(self.options.get('headless', False)),
                accept_downloads=True,
                downloads_path=str(self.temp),
                firefox_user_prefs={'pdfjs.disabled': True},
            )
        except Exception:  # noqa: BLE001 - Firefox missing or profile locked
            raise sb.SatError('sat_navegador_no_disponible') from None
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.goto(self.options['base_url'], wait_until='domcontentloaded', timeout=90_000)
        sb.guided_entry(self.page)

    def sign_in(self):
        """e.firma desde el gestor, sin escribirla en disco. Si algo no aparece, la persona sigue a mano."""
        if not self.fiel:
            return 'manual'
        page = self.page
        try:
            for text in sel.FIEL_BUTTON_TEXTS:
                button = page.get_by_text(text, exact=True).first
                if button.count():
                    button.click(timeout=sel.FIEL_WAIT_MS)
                    break
            page.locator(sel.FIEL_CER_INPUT).first.set_input_files(
                {
                    'name': self.fiel['cer_name'] or 'fiel.cer',
                    'mimeType': 'application/octet-stream',
                    'buffer': self.fiel['cer'],
                },
                timeout=sel.FIEL_WAIT_MS,
            )
            page.locator(sel.FIEL_KEY_INPUT).first.set_input_files(
                {
                    'name': self.fiel['key_name'] or 'fiel.key',
                    'mimeType': 'application/octet-stream',
                    'buffer': self.fiel['key'],
                },
                timeout=sel.FIEL_WAIT_MS,
            )
            page.locator(sel.FIEL_PASSWORD_INPUT).first.fill(self.fiel['password'], timeout=sel.FIEL_WAIT_MS)
            page.locator(sel.FIEL_SUBMIT).first.click(timeout=sel.FIEL_WAIT_MS)
            return 'fiel'
        except Exception:  # noqa: BLE001 - never guess: the person finishes signing in
            return 'manual'
        finally:
            self.fiel = None  # la FIEL sólo vive lo necesario

    def rows(self, login_timeout, stop):
        consulta = sb._wait_consulta(self.context, login_timeout, stop, lambda e: None)
        if consulta is None:
            raise sb.SatError('sat_cancelado' if stop() else 'sat_sin_consulta')
        self.page = consulta
        table = consulta.locator('table tbody tr')
        if table.count() == 0:
            table = consulta.locator('table tr')
        heads = consulta.locator('table th')
        columns = sb.column_map([heads.nth(i).inner_text(timeout=800) for i in range(heads.count())])
        found = []
        for i in range(min(table.count(), sb.MAX_ROWS)):
            cells = table.nth(i).locator('td')
            if cells.count() < 2:
                continue
            texts = [cells.nth(j).inner_text(timeout=800) for j in range(cells.count())]
            parsed = sb.row_entry(texts, columns)
            if not parsed:
                continue
            found.append(
                {
                    'indice': i,
                    'operacion': parsed[0],
                    'tipo': parsed[1],
                    'periodo': parsed[2],
                    'ejercicio': sb.row_year(texts, columns),
                    'con_pdf': sb.find_pdf_control(table.nth(i)) is not None,
                }
            )
        if not any(r['con_pdf'] for r in found):
            raise sb.SatError('sat_sin_controles')  # sin icono PDF no se hace ningún clic
        return found

    def download(self, row):
        if self.page.is_closed():
            raise sb.SatError('sat_navegador_cerrado')
        if not row.get('con_pdf'):
            raise RowError('sin_control')
        rows = self.page.locator('table tbody tr')
        if rows.count() <= row['indice']:
            rows = self.page.locator('table tr')
        control = sb.find_pdf_control(rows.nth(row['indice']))
        if control is None:
            raise RowError('sin_control')
        try:
            control.scroll_into_view_if_needed(timeout=5000)
            with self.page.expect_download(timeout=ROW_TIMEOUT_MS) as waiting:
                control.click(timeout=10_000)
        except Exception as error:  # noqa: BLE001 - Playwright's timeout is its own class
            if 'timeout' in type(error).__name__.lower() or 'timeout' in str(error).lower():
                raise TimeoutError from None
            raise RowError('descarga_fallida') from None
        download = waiting.value
        target = sb.unique_path(self.temp, download.suggested_filename or 'declaracion.pdf')
        download.save_as(str(target))
        if target.stat().st_size > sb.MAX_PDF_BYTES:
            target.unlink(missing_ok=True)
            raise RowError('demasiado_grande')
        self.page.wait_for_timeout(sel.ROW_PAUSE_MS)
        return target

    def close(self):
        try:
            if self.context is not None:
                self.context.close()
            if self.playwright is not None:
                self.playwright.stop()
        finally:
            shutil.rmtree(self.temp, ignore_errors=True)


# ---------------------------------------------------------------- sesión completa


def existing_operations(folder):
    """Números de operación de los PDF que ya están en la carpeta, desde su índice."""
    index = declara_folder.read_json(declara_folder.internal(folder) / declara_folder.INDEX, {})
    return {
        str((item.get('info') or {}).get('operation'))
        for item in index.get('archivos', {}).values()
        if (item.get('info') or {}).get('operation')
    }


def run(payload, roots, user, machine, options, report, fetch_fiel=None, portal_class=Portal):
    """Un trabajo `declara_carpeta` con `op: sat`. `report(evento) -> órdenes de la web`."""
    guard = declara_folder.Guard(roots)
    folder = guard.check(payload['ruta'])
    short_name, rfc = payload['nombre_corto'], payload.get('rfc')
    stages = {'agente': 'hecho', 'firefox': 'pendiente', 'sesion': 'pendiente', 'consulta': 'pendiente',
              'descarga': 'pendiente', 'reanalisis': 'pendiente'}  # fmt: skip

    def send(event):
        return report({**event, 'etapas': dict(stages)}) or {}

    # La carpeta se analiza primero: toma el bloqueo, actualiza el índice y da los números de operación existentes.
    first = declara_folder.analyze(guard, folder, short_name, rfc, user, machine)
    if first['solo_lectura']:
        raise declara_folder.FolderError('carpeta_bloqueada')
    existing = existing_operations(folder) if payload.get('solo_faltantes', True) else set()
    sat = dict(options.get('sat') or {})
    if payload.get('persona') == 'fisica' and sat.get('base_url_fisicas'):
        sat['base_url'] = sat['base_url_fisicas']
    if not sat.get('base_url'):
        raise sb.SatError('sat_no_habilitado')
    fiel = fetch_fiel() if payload.get('metodo') == 'fiel' and fetch_fiel else None
    portal = portal_class(sat, send, fiel)
    fiel = None
    orders = {}
    try:
        stages['firefox'] = 'en_curso'
        send({'etapa': 'abriendo'})
        portal.open()
        stages['firefox'] = 'hecho'
        stages['sesion'] = 'en_curso'
        how = portal.sign_in()
        send({'etapa': 'esperando_sesion', 'acceso': how})
        stop = lambda: bool(orders.get('cancelar'))  # noqa: E731
        found = portal.rows(float(sat.get('login_timeout', 600)), stop)
        stages['sesion'] = 'hecho'
        stages['consulta'] = 'hecho'
        rows = [
            {k: v for k, v in r.items()} | {'fila': n}
            for n, r in enumerate(found, start=1)
            if wanted(r, payload.get('periodo') or '', payload.get('ejercicio'))
        ]
        stages['descarga'] = 'en_curso'
        send({'etapa': 'consulta', 'encontradas': len(found), 'total': len(rows), 'filas': public(rows)})

        def save(path, row):
            # Red perdida al guardar: la cola espera, reintenta la conexión (3 veces) y sigue; si no vuelve, la fila
            # queda con error y el resto continúa.
            state, name = declara_folder.with_reconnect(
                declara_folder.save_downloaded, guard, folder, path, short_name, rfc, user, machine
            )
            existing.add(row.get('operacion'))
            return state, name

        def notify(event):
            nonlocal orders
            orders = send({**event, 'encontradas': len(found)})
            return orders

        summary = run_queue(rows, portal.download, save, existing, notify)
        stages['descarga'] = 'hecho'
    finally:
        portal.close()
    stages['reanalisis'] = 'en_curso'
    send(
        {
            'etapa': 'reanalizando',
            **{k: summary[k] for k in ('total', 'procesadas', 'guardadas', 'ya_existian', 'errores')},
        }
    )
    final = declara_folder.analyze(guard, folder, short_name, rfc, user, machine)
    stages['reanalisis'] = 'hecho'
    final['sesion'] = {
        'encontradas': len(found),
        'filas': public(summary['filas']),
        **{k: summary[k] for k in ('total', 'procesadas', 'guardadas', 'ya_existian', 'errores', 'cancelada')},
        'etapas': stages,
        'acceso': how,
    }
    return final


def browser_state(options):
    """Lo que la tarjeta «Sesión SAT» necesita saber del equipo, sin abrir nada."""
    sat = options.get('sat') or {}
    try:
        import playwright  # noqa: F401

        playwright_ok = True
    except ImportError:
        playwright_ok = False
    browsers = Path(sat.get('browsers_dir') or '')
    firefox = (
        bool(sat.get('browsers_dir'))
        and browsers.is_dir()
        and any(p.name.startswith('firefox') for p in browsers.iterdir())
    )
    return {
        'playwright': playwright_ok,
        'firefox': firefox,
        'portal': bool(sat.get('base_url')),
        'portal_fisicas': bool(sat.get('base_url_fisicas')),
        'navegacion': 'Portal → Personas morales → «Pagos provisionales del ISR»',
    }


def install_firefox(options):
    """Instala el Firefox dedicado de Playwright en la carpeta del agente (lo pide la persona desde la web)."""
    import os
    import subprocess
    import sys

    sat = options.get('sat') or {}
    env = {**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': str(sat.get('browsers_dir') or '')}
    done = subprocess.run(
        [sys.executable, '-m', 'playwright', 'install', 'firefox'], env=env, capture_output=True, timeout=900
    )
    if done.returncode != 0:
        raise sb.SatError('sat_navegador_no_disponible')
    return browser_state(options)
