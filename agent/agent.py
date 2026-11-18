"""Outbound-only local worker. Supported operation in 0.1: read-only folder inventory."""

import argparse
import json
import logging
import os
from pathlib import Path
from urllib.request import Request, urlopen, build_opener, ProxyHandler
from urllib.error import URLError
from urllib.parse import urlparse
import threading

MAX_FILES = 3000


def request(url, token, path, data):
    req = Request(
        url.rstrip('/') + '/api' + path,
        data=json.dumps(data).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        method='POST',
    )
    opener = (
        build_opener(ProxyHandler({})).open if urlparse(url).hostname in {'localhost', '127.0.0.1', '::1'} else urlopen
    )
    with opener(req, timeout=20) as response:
        return json.load(response)


def safe_inventory(folder, allowed_roots, rfc=''):
    """Use the same path/link checks and secret exclusions as CS-Storage; metadata only."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    from app.storage.local import LocalFolderProvider
    from app.storage.providers import ScanIssue
    from app.pilot_scan import SECRET_PATTERNS

    provider = LocalFolderProvider(Path(folder), tuple(Path(p) for p in allowed_roots), exclusions=SECRET_PATTERNS)
    files = []
    warnings = []
    size = 0
    truncated = False
    for entry in provider.enumerate():
        if isinstance(entry, ScanIssue):
            warnings.append('Incidencia de recorrido: ' + entry.code)
            if entry.code == 'scan_limit':
                truncated = True
            continue
        row = {
            'name': Path(entry.key).name,
            'relative_path': entry.key,
            'extension': Path(entry.key).suffix.lower(),
            'size': entry.size,
        }
        cost = len(json.dumps(row).encode()) + 2
        if len(files) >= MAX_FILES or size + cost > 1_500_000:
            truncated = True
            break
        files.append(row)
        size += cost
    summary, summary_warnings, summary_truncated, sections = classify_folder(folder, allowed_roots, rfc)
    return {
        'files': files,
        'summary': summary,
        **sections,  # one entry per virtual group with its own structure: cfdi, impuestos…
        'truncated': truncated or summary_truncated,
        'warnings': list(dict.fromkeys(warnings + summary_warnings))[:10],
        'catalog_imported': False,
        'content_analyzed': False,
        'read_only': True,
    }


XML_HEAD_BYTES = 16384
MAX_XML_HEADS = 20000


def classify_folder(folder, allowed_roots, rfc=''):
    """Group EVERY file by type (any extension) with the same path/link checks as the inventory.

    Only names, sizes and extensions are used, plus the first 8 KB of each XML to tell a CFDI's type (ingreso, egreso,
    pago, nómina). e.firma/CSD material and password notes are counted but never opened and never named.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    from app.folder_groups import GROUPS, CfdiIndex, Summary, classify, cfdi_info
    from app.storage.local import LocalFolderProvider
    from app.storage.providers import ScanIssue, StorageError
    from app.expediente_groups import ExpedienteIndex
    from app.finance_groups import FinanceIndex
    from app.imss_groups import ImssIndex
    from app.payroll_groups import PayrollIndex, WorkersIndex
    from app.tax_groups import TaxIndex

    class AllFiles(LocalFolderProvider):
        def _supported(self, key):  # every extension is counted; nothing here is returned as content
            return True

    provider = AllFiles(Path(folder), tuple(Path(p) for p in allowed_roots), max_seconds=120, max_entries=60000)
    summary, index, taxes, imss = Summary(), CfdiIndex(rfc), TaxIndex(), ImssIndex()
    expediente, finance, payroll, workers = ExpedienteIndex(rfc), FinanceIndex(), PayrollIndex(), WorkersIndex()
    # Which index receives each group's files; the CFDI XML and the payroll PDFs are routed above.
    routes = {
        'cfdi_pdf': (index.add_pdf,),
        'sat_reportes': (index.add_report,),
        'impuestos': (taxes.add,),
        'imss': (imss.add,),
        'legal': (expediente.add,),
        'identificaciones': (expediente.add,),
        'estados_financieros': (finance.add,),
        'trabajadores': (workers.add,),
    }
    warnings, truncated, heads = [], False, 0
    for entry in provider.enumerate():
        if isinstance(entry, ScanIssue):
            warnings.append('Incidencia de recorrido: ' + entry.code)
            truncated = truncated or entry.code == 'scan_limit'
            continue
        tipo = None
        if entry.key.lower().endswith('.xml') and heads < MAX_XML_HEADS:
            heads += 1
            try:
                with provider.open_read(entry.key) as handle:
                    info = cfdi_info(handle.read(XML_HEAD_BYTES))
                tipo = info['tipo'] if info else ''
                if info:
                    index.add_xml(entry.key, info)
            except StorageError:
                index.add_xml(entry.key, None)  # unreadable or too large: reviewed by a person
        group = summary.add(entry.key, entry.size, tipo)
        if group == 'cfdi_xml' and tipo == 'N':
            payroll.add_xml(entry.key)
        elif group == 'nomina' and entry.key.lower().endswith('.pdf'):
            payroll.add_pdf(entry.key)
        for target in routes.get(group, ()):
            target(entry.key)
    result = summary.result()
    result['xml_headers_read'] = heads
    sensitive = sum(g['count'] for g in result['groups'] if GROUPS[g['key']][1])
    if sensitive:
        warnings.append(f'{sensitive} archivos de credenciales o contraseñas se contaron sin abrirse.')
    sections = {
        'cfdi': index.result(),
        'impuestos': taxes.result(),
        'imss': imss.result(),
        'expediente': expediente.result(),
        'finanzas': finance.result(),
        'nomina': payroll.result(),
        'trabajadores': workers.result(),
    }
    return result, warnings, truncated, sections


def run(config, stop_event=None, request_fn=request):
    stop_event = stop_event or threading.Event()
    url = config['api_url']
    parsed = urlparse(url)
    if parsed.scheme != 'https' and not (
        parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'}
    ):
        raise ValueError('La API remota necesita HTTPS.')
    token = config['token']
    agent_id = config['agent_id']
    roots = config['allowed_roots']
    if len(token) < 24:
        raise ValueError('Token del agente no configurado.')
    pending = None
    from urllib.parse import urlencode

    suffix = '?' + urlencode({'not_before': config['not_before']}) if config.get('not_before') else ''
    while not stop_event.is_set():
        try:
            request_fn(url, token, '/agent/heartbeat', {'id': agent_id, 'capabilities': ['scan_folder']})
            if pending:
                try:
                    request_fn(url, token, '/agent/jobs/' + pending[0] + '/result', pending[1])
                except __import__('urllib.error', fromlist=['HTTPError']).HTTPError as error:
                    if error.code != 409:
                        raise
                pending = None
            if stop_event.is_set():
                break
            job = request_fn(url, token, '/agent/' + agent_id + '/claim' + suffix, {})
            if job:
                logging.info('Procesando trabajo %s', job['id'])
                try:
                    if job['kind'] != 'scan_folder':
                        raise ValueError('Operación no admitida')
                    result = safe_inventory(job['payload']['folder'], roots, job['payload'].get('rfc', ''))
                    status = 'completed'
                except Exception as exc:  # noqa: BLE001 - any failure ends the job with its data-free reason
                    logging.exception('Trabajo %s: no se pudo analizar la carpeta', job['id'])
                    result = reason(exc)
                    status = 'failed'
                pending = (job['id'], {'agent_id': agent_id, 'status': status, 'result': result})
                continue
        except (URLError, TimeoutError, OSError, ValueError):
            logging.warning('Agente sin comunicación; reintento pendiente.')
        stop_event.wait(5)


# ---------------------------------------------------------------- linked mode (Bloque 4, option A)

# Data-free explanations of why a folder could not be read, shown to the user who asked for the analysis.
REASONS = {
    'unauthorized_root': 'La ruta está fuera de las carpetas autorizadas por la administración.',
    'root_unavailable': 'La carpeta no existe o no está disponible en este equipo.',
    'missing': 'La carpeta no existe en este equipo.',
    'access_denied': 'Tu usuario de Windows no tiene permiso de lectura en la carpeta.',
    'invalid_path': 'La ruta no es válida o usa un enlace o unión que no se permite.',
    'smb_not_configured': 'Las carpetas de red no están habilitadas para el agente.',
    'invalid_configuration': 'La configuración de carpetas autorizadas no es válida.',
    'read_error': 'No se pudo leer la carpeta.',
}


def reason(exc):
    code = getattr(exc, 'code', None) or (exc.args[0] if exc.args and isinstance(exc.args[0], str) else '')
    return {'error': REASONS.get(code, 'No se pudo analizar la carpeta.'), 'error_code': code or 'unknown'}


def default_agent_id():
    """One agent per Windows session: computer and Windows user."""
    import re

    raw = (os.getenv('COMPUTERNAME', 'equipo') + '-' + os.getenv('USERNAME', 'usuario')).lower()
    return ('pc-' + re.sub(r'[^a-z0-9_-]+', '-', raw))[:80]


def post(url, path, data, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = Request(url.rstrip('/') + '/api' + path, data=json.dumps(data).encode(), headers=headers, method='POST')
    opener = (
        build_opener(ProxyHandler({})).open if urlparse(url).hostname in {'localhost', '127.0.0.1', '::1'} else urlopen
    )
    with opener(req, timeout=20) as response:
        return json.load(response)


class LinkedAgent:
    """Paired at the user's sign-in through http://127.0.0.1:<local_port>; the credential lives in memory only."""

    def __init__(self, config, post_fn=post):
        url = config['api_url']
        parsed = urlparse(url)
        if parsed.scheme != 'https' and not (
            parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'}
        ):
            raise ValueError('La API remota necesita HTTPS.')
        self.url = url
        self.agent_id = config.get('agent_id') or default_agent_id()
        self.machine = config.get('machine') or os.getenv('COMPUTERNAME', '')
        self.port = int(config.get('local_port', 47865))
        origin = parsed.scheme + '://' + parsed.netloc
        self.origins = set(config.get('app_origins') or [origin])
        self.post = post_fn
        self.lock = threading.Lock()
        self.token = None
        self.user = None
        self.notice = 'Sin vincular: inicia sesión en ContaSuite en este equipo.'

    def pair(self, code):
        result = self.post(self.url, '/agent/pair', {'code': code, 'agent_id': self.agent_id, 'machine': self.machine})
        with self.lock:
            self.token, self.user = result['token'], result['user']
            self.notice = 'Vinculado como ' + result['user']
        logging.info('Agente vinculado.')
        return {'paired': True, 'user': result['user'], 'agent_id': self.agent_id}

    def unpair(self, notice):
        with self.lock:
            self.token, self.user, self.notice = None, None, notice
        logging.info('Agente desvinculado: %s', notice)

    def status(self):
        with self.lock:
            return {
                'agent_id': self.agent_id,
                'machine': self.machine,
                'paired': bool(self.token),
                'user': self.user,
                'notice': self.notice,
            }

    def work(self, stop_event):
        from urllib.error import HTTPError

        pending = None
        while not stop_event.is_set():
            with self.lock:
                token = self.token
            if not token:
                stop_event.wait(2)
                continue
            try:
                beat = self.post(
                    self.url, '/agent/heartbeat', {'id': self.agent_id, 'capabilities': ['scan_folder']}, token
                )
                if beat.get('restart'):
                    self.unpair('Reinicio solicitado por la administración: inicia sesión de nuevo.')
                    continue
                if pending:
                    try:
                        self.post(self.url, '/agent/jobs/' + pending[0] + '/result', pending[1], token)
                    except HTTPError as error:
                        if error.code != 409:
                            raise
                    pending = None
                job = self.post(self.url, '/agent/' + self.agent_id + '/claim', {}, token)
                if job:
                    logging.info('Procesando trabajo %s', job['id'])
                    try:
                        if job['kind'] != 'scan_folder':
                            raise ValueError('Operación no admitida')
                        result = safe_inventory(job['payload']['folder'], job['payload'].get('roots') or [], job['payload'].get('rfc', ''))
                        status = 'completed'
                    except Exception as exc:  # noqa: BLE001 - every failure ends the job with its data-free reason
                        logging.exception('Trabajo %s: no se pudo analizar la carpeta', job['id'])
                        result, status = reason(exc), 'failed'
                    pending = (job['id'], {'agent_id': self.agent_id, 'status': status, 'result': result})
                    continue
            except HTTPError as error:
                if error.code in (401, 403):
                    self.unpair('Vínculo terminado: inicia sesión en ContaSuite de nuevo.')
                    pending = None
                    continue
                logging.warning('Respuesta inesperada del servidor (%s); reintento pendiente.', error.code)
            except (URLError, TimeoutError, OSError, ValueError):
                logging.warning('Agente sin comunicación; reintento pendiente.')
            stop_event.wait(5)

    def handler(self):
        from http.server import BaseHTTPRequestHandler

        agent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):  # no request lines (they could carry codes) in the log
                return

            def allowed(self):
                return self.headers.get('Origin', '') in agent.origins

            def cors(self):
                origin = self.headers.get('Origin', '')
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                # Private Network Access: a page of the app may call this loopback agent.
                self.send_header('Access-Control-Allow-Private-Network', 'true')
                self.send_header('Access-Control-Max-Age', '600')

            def reply(self, code, data):
                body = json.dumps(data).encode()
                self.send_response(code)
                if self.allowed():
                    self.cors()
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):  # noqa: N802 - http.server naming
                self.send_response(204 if self.allowed() else 403)
                if self.allowed():
                    self.cors()
                self.send_header('Content-Length', '0')
                self.end_headers()

            def do_GET(self):  # noqa: N802
                if not self.allowed():
                    return self.reply(403, {})
                if self.path != '/status':
                    return self.reply(404, {})
                return self.reply(200, agent.status())

            def do_POST(self):  # noqa: N802
                if not self.allowed() or self.path != '/pair':
                    return self.reply(403, {})
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if length > 1024:
                        return self.reply(413, {})
                    code = json.loads(self.rfile.read(length) or b'{}').get('code', '')
                    if not isinstance(code, str) or not 8 <= len(code) <= 64:
                        return self.reply(422, {'error': 'Código inválido.'})
                    return self.reply(200, agent.pair(code))
                except Exception:  # noqa: BLE001 - the browser gets a generic answer; details stay in the log
                    logging.exception('No se pudo vincular el agente.')
                    return self.reply(502, {'error': 'No se pudo vincular el agente con ContaSuite.'})

        return Handler

    def serve(self, stop_event=None):
        from http.server import ThreadingHTTPServer

        stop_event = stop_event or threading.Event()
        server = ThreadingHTTPServer(('127.0.0.1', self.port), self.handler())
        threading.Thread(target=self.work, args=(stop_event,), daemon=True).start()
        threading.Thread(target=server.serve_forever, daemon=True).start()
        logging.info('Agente %s esperando vinculación en 127.0.0.1:%s.', self.agent_id, self.port)
        try:
            stop_event.wait()
        finally:
            server.shutdown()


def main(argv=None):
    """Launcher. Linked mode (no token in the configuration) is the default since Bloque 4; a configuration with
    `token` keeps the former shared-token mode, which the server only accepts during a transition."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=str(Path(__file__).with_name('config.json')))
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    parsed = urlparse(config['api_url'])
    if parsed.scheme != 'https' and not (
        parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'}
    ):
        raise SystemExit('La API remota necesita HTTPS. HTTP sólo está permitido en localhost.')
    log_file = config.get('log_file')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(message)s',
        **({'filename': log_file, 'encoding': 'utf-8'} if log_file else {}),
    )
    token = os.getenv('CONTA_AGENT_TOKEN') or config.get('token', '')
    if not token:
        agent = LinkedAgent(config)
        if config.get('tray', True):
            import sys

            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import tray

            if tray.available():
                # The icon needs the main thread; the agent works in the background until «Detener el agente».
                stop_event = threading.Event()
                threading.Thread(target=agent.serve, args=(stop_event,), daemon=True).start()
                tray.run(agent, (config.get('app_origins') or [config['api_url']])[0], log_file, stop_event)
                return
            logging.info('Sin icono en el área de notificación (pystray no instalado).')
        agent.serve()
        return
    if not config.get('allowed_roots'):
        raise SystemExit('Configura allowed_roots con las carpetas autorizadas antes de iniciar.')
    if len(token) < 24:
        raise SystemExit('Configura el token del agente (mínimo 24 caracteres).')
    logging.info('Agente %s iniciado (modo de token compartido, transición).', config['agent_id'])
    run({**config, 'token': token})


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nAgente detenido.')
