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
CAPABILITIES = ['scan_folder', 'export_virtual']


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


def safe_inventory(folder, allowed_roots, rfc='', with_index=False):
    """Use the same path/link checks and secret exclusions as CS-Storage; metadata only.

    With `with_index` the result also carries `_index` (one row per file, with its SHA-256) and `_complete` for the
    persistent virtual index; the caller sends them in batches and removes them before delivering the result.
    """
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
    scan = scan_tree(folder, allowed_roots, rfc)
    summary, summary_warnings, summary_truncated, sections = inventory_from_scan(scan)
    extra = {'_index': index_rows(scan), '_complete': not scan.truncated} if with_index else {}
    return {
        **extra,
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
MAX_PAYMENT_BYTES = 2_000_000
MAX_REPORT_BYTES = 8_000_000


def read_cfdi(provider, entry):
    """(info, uuid, payment text) of a CFDI XML. Payment text is only returned for tipo P (to find what it settles)."""
    from app.folder_groups import cfdi_info
    from app.sat_reconcile import uuid_in

    with provider.open_read(entry.key) as handle:
        info = cfdi_info(handle.read(XML_HEAD_BYTES))
        if not info:
            return None, None, None
        uuid, text = uuid_in(Path(entry.key).name), None
        if info['tipo'] == 'P' and entry.size <= MAX_PAYMENT_BYTES:
            handle.seek(0)
            text = handle.read(MAX_PAYMENT_BYTES).decode('utf-8', errors='ignore')
            uuid = uuid or uuid_in(text[-4096:])
        elif not uuid:  # the stamp (TimbreFiscalDigital) closes the document
            handle.seek(max(0, entry.size - 4096))
            uuid = uuid_in(handle.read(4096).decode('utf-8', errors='ignore'))
    return info, uuid, text


def read_report(provider, entry, reconcile):
    """Feed one SAT monthly report (.xls) to the reconciliation. False when it cannot be read."""
    from app.folder_groups import REPORT_NAME
    from app.storage.providers import StorageError
    from app.xls_reader import read_rows

    match = REPORT_NAME.match(Path(entry.key).name)
    if not match:
        return True
    try:
        with provider.open_read(entry.key) as handle:
            rows = read_rows(handle.read(MAX_REPORT_BYTES))
    except (StorageError, ValueError):
        return False
    reconcile.add_report(
        'E' if match.group(1).lower() == 'emitid' else 'R', int(match.group(2)), int(match.group(3)), rows
    )
    return True


def read_certificate(provider, entry, certs):
    """Validity of a PUBLIC .cer. Private keys never reach this function (they are not .cer files)."""
    from app.storage.providers import StorageError

    try:
        with provider.open_read(entry.key) as handle:
            data = handle.read(65536)
    except StorageError:
        return
    certs.add(entry.key, data)


def scan_tree(folder, allowed_roots, rfc=''):
    """Walk EVERY file of a company folder (any extension) with the same path/link checks as the inventory.

    Returns what the walk learned: the files with their group and one index per document group. Only names, sizes and
    extensions are used, plus the beginning of each CFDI XML (type, date, RFCs, UUID), the SAT monthly reports and the
    PUBLIC .cer certificates. Private keys and password notes are never opened.
    """
    import sys
    from types import SimpleNamespace

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    from app.folder_groups import CfdiIndex, Summary
    from app.storage.local import LocalFolderProvider
    from app.storage.providers import ScanIssue, StorageError
    from app.cert_groups import CertIndex
    from app.sat_reconcile import PpdIndex, SatReconcile
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
    reconcile, ppd, certs = SatReconcile(), PpdIndex(), CertIndex(rfc)
    warnings, truncated, heads, unreadable, entries, mtimes = [], False, 0, 0, [], {}
    for entry in provider.enumerate():
        if isinstance(entry, ScanIssue):
            warnings.append('Incidencia de recorrido: ' + entry.code)
            truncated = truncated or entry.code == 'scan_limit'
            continue
        tipo = None
        lower = entry.key.lower()
        if lower.endswith('.xml') and heads < MAX_XML_HEADS:
            heads += 1
            try:
                info, uuid, payment = read_cfdi(provider, entry)
                tipo = info['tipo'] if info else ''
                if info:
                    place = index.add_xml(entry.key, info)
                    reconcile.add_xml(uuid, entry.key, place)
                    ppd.add_invoice(uuid, entry.key, info, place)
                    if payment:
                        ppd.add_payment(entry.key, payment)
            except StorageError:
                index.add_xml(entry.key, None)  # unreadable or too large: reviewed by a person
        group = summary.add(entry.key, entry.size, tipo)
        entries.append((entry.key, entry.size, group))
        mtimes[entry.key] = entry.mtime_ns
        if group == 'cfdi_xml' and tipo == 'N':
            payroll.add_xml(entry.key)
        elif group == 'nomina' and lower.endswith('.pdf'):
            payroll.add_pdf(entry.key)
        elif group == 'sat_reportes' and lower.endswith('.xls'):
            if not read_report(provider, entry, reconcile):
                unreadable += 1
        elif group == 'credenciales' and lower.endswith('.cer'):
            read_certificate(provider, entry, certs)
        for target in routes.get(group, ()):
            target(entry.key)
    return SimpleNamespace(
        provider=provider,
        entries=entries,
        mtimes=mtimes,
        summary=summary,
        warnings=warnings,
        truncated=truncated,
        heads=heads,
        unreadable=unreadable,
        index=index,
        taxes=taxes,
        imss=imss,
        expediente=expediente,
        finance=finance,
        payroll=payroll,
        workers=workers,
        reconcile=reconcile,
        ppd=ppd,
        certs=certs,
    )


def classify_folder(folder, allowed_roots, rfc=''):
    """Group every file by type and build the inventory of each document group (see `scan_tree`)."""
    return inventory_from_scan(scan_tree(folder, allowed_roots, rfc))


def inventory_from_scan(scan):
    """(summary, warnings, truncated, sections) of a finished scan."""
    from app.folder_groups import GROUPS

    result = scan.summary.result()
    result['xml_headers_read'] = scan.heads
    warnings = list(scan.warnings)
    sensitive = sum(g['count'] for g in result['groups'] if GROUPS[g['key']][1])
    if sensitive:
        warnings.append(
            f'{sensitive} archivos de credenciales o contraseñas: sólo se leyó la vigencia de los .cer públicos.'
        )
    if scan.unreadable:
        warnings.append(f'{scan.unreadable} reportes .xls del SAT no se pudieron leer.')
    sections = {
        'conciliacion': scan.reconcile.result(),
        'ppd': scan.ppd.result(),
        'certificados': scan.certs.result(),
        'cfdi': scan.index.result(),
        'impuestos': scan.taxes.result(),
        'imss': scan.imss.result(),
        'expediente': scan.expediente.result(),
        'finanzas': scan.finance.result(),
        'nomina': scan.payroll.result(),
        'trabajadores': scan.workers.result(),
    }
    return result, warnings, scan.truncated, sections


def virtual_maps(scan):
    """Where each group's index places its files. Later placements win: payroll XML belong to Nómina, not CFDI."""
    return [
        scan.index.virtual(),
        scan.taxes.virtual(),
        scan.imss.virtual(),
        scan.expediente.virtual(),
        scan.finance.virtual(),
        scan.workers.virtual(),
        scan.payroll.virtual(),
    ]


def sha256_of(provider, key):
    """SHA-256 of a file read through the provider; None when it cannot be read (too large, changed, no access)."""
    import hashlib

    from app.storage.providers import StorageError

    try:
        digest = hashlib.sha256()
        with provider.open_read(key) as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(block)
        return digest.hexdigest()
    except StorageError:
        return None


def index_rows(scan):
    """One row per file for the persistent virtual index. Credentials, password notes and system files are not in
    it (they are only counted); every other file is read once to get its SHA-256, which lets the server follow moves."""
    from app.export_plan import SECTIONS, build_plan

    groups = {key: group for key, _, group in scan.entries}
    plan = build_plan(scan.entries, virtual_maps(scan), list(SECTIONS), 0)
    return [
        {
            'p': item.key,
            's': item.size,
            'm': scan.mtimes.get(item.key),
            'h': sha256_of(scan.provider, item.key),
            'g': groups[item.key],
            'sec': item.section,
            'v': '/'.join((*item.parts, item.name)),
            'st': 'revisar' if 'Por revisar' in item.parts else 'ok',
        }
        for item in plan['items']
    ]


INDEX_BATCH = 400


def send_index(send, job_id, agent_id, result):
    """Send the scan's files to the server in batches and remove them from the result. The last batch closes the scan;
    a walk that hit its limit says so, so the server does not treat the rest as missing."""
    rows = result.pop('_index', None)
    complete = result.pop('_complete', True)
    if rows is None:
        return
    batches = [rows[i : i + INDEX_BATCH] for i in range(0, len(rows), INDEX_BATCH)] or [[]]
    try:
        for n, batch in enumerate(batches):
            send(
                '/agent/jobs/' + job_id + '/index',
                {'agent_id': agent_id, 'seq': n, 'rows': batch, 'last': n == len(batches) - 1, 'complete': complete},
            )
    except Exception:  # noqa: BLE001 - the analysis is delivered even if the index could not be stored
        logging.warning('No se pudo guardar el índice virtual; el análisis se entrega igual.')


def export_virtual(payload, allowed_roots):
    """Preview (apply false) or run (apply true) the export of a COPY of the folder in the virtual order.

    The destination is checked twice: by its text (inside an authorized root, outside the company folder) and on disk
    (resolved path, no links, nothing inside it yet). The originals are only read.
    """
    import shutil
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    from app.export_copy import execute
    from app.export_plan import build_plan, destination_problem, preview
    from app.storage.paths import check_no_links
    from app.storage.providers import StorageError

    folder, destination = payload['folder'], str(payload.get('destination') or '')
    problem = destination_problem(destination, folder, allowed_roots)
    if problem:
        raise StorageError(problem)
    target = Path(destination)
    # The nearest folder that already exists decides: it must be a real path (no links) inside an authorized root.
    anchor = next(p for p in (target, *target.parents) if p.exists())
    try:
        check_no_links(anchor)
    except StorageError:
        raise StorageError('invalid_path') from None
    real = anchor.resolve()
    if not any(real.is_relative_to(Path(r).resolve()) for r in allowed_roots):
        raise StorageError('destino_fuera_de_raices')
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise StorageError('destino_no_vacio')
    scan = scan_tree(folder, allowed_roots, payload.get('rfc', ''))
    plan = build_plan(scan.entries, virtual_maps(scan), payload.get('include'), len(destination))
    if not payload.get('apply'):
        result = preview(plan, destination, shutil.disk_usage(anchor).free)
        result['truncated'] = scan.truncated
        return result
    if scan.truncated:
        raise StorageError('read_error')  # an incomplete walk would produce an incomplete copy
    return execute(scan.provider, plan['items'], destination)


def run_job(job, roots):
    """(status, result) of one claimed job. Never raises: every failure becomes its data-free reason."""
    try:
        payload = job['payload']
        if job['kind'] == 'scan_folder':
            return 'completed', safe_inventory(payload['folder'], roots, payload.get('rfc', ''), with_index=True)
        if job['kind'] == 'export_virtual':
            return 'completed', export_virtual(payload, roots)
        raise ValueError('Operación no admitida')
    except Exception as exc:  # noqa: BLE001 - any failure ends the job with its data-free reason
        logging.exception('Trabajo %s: no se pudo completar', job.get('id'))
        return 'failed', reason(exc)


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
            request_fn(url, token, '/agent/heartbeat', {'id': agent_id, 'capabilities': CAPABILITIES})
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
                status, result = run_job(job, roots)
                send_index(lambda path, data: request_fn(url, token, path, data), job['id'], agent_id, result)
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
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    from app.export_plan import REASONS as EXPORT_REASONS

    code = getattr(exc, 'code', None) or (exc.args[0] if exc.args and isinstance(exc.args[0], str) else '')
    return {
        'error': {**REASONS, **EXPORT_REASONS}.get(code, 'No se pudo completar la operación.'),
        'error_code': code or 'unknown',
    }


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

    def run_alive(self, job, token):
        """Run a job in its own thread while the heartbeat continues: a long export must not look like a dead agent."""
        outcome = []
        worker = threading.Thread(
            target=lambda: outcome.append(run_job(job, job['payload'].get('roots') or [])), daemon=True
        )
        worker.start()
        while worker.is_alive():
            worker.join(5)
            try:
                self.post(self.url, '/agent/heartbeat', {'id': self.agent_id, 'capabilities': CAPABILITIES}, token)
            except (URLError, TimeoutError, OSError, ValueError):
                pass  # the main loop handles a lost connection or a revoked link once the job is done
        return outcome[0]

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
                    self.url, '/agent/heartbeat', {'id': self.agent_id, 'capabilities': CAPABILITIES}, token
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
                    status, result = self.run_alive(job, token)
                    send_index(
                        lambda path, data, token=token: self.post(self.url, path, data, token),
                        job['id'],
                        self.agent_id,
                        result,
                    )
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
