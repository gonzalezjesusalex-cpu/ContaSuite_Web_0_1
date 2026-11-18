"""Fase 1 del navegador del agente: lógica pura y descarga contra un SAT simulado (sin tocar el portal real)."""

import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

AGENT = Path(__file__).resolve().parents[2] / 'agent'
sys.path.insert(0, str(AGENT))
import sat_browser as sb  # noqa: E402

PDF = b'%PDF-1.4 declaracion simulada'

PAGE = """<html><body><h1>Consulta de declaraciones (simulada)</h1>
<table><thead><tr><th>PDF</th><th>No. de operación</th><th>Tipo de declaración</th><th>Ejercicio</th><th>Periodo</th></tr></thead>
<tbody>
<tr><td><a href="/pdf/1"><img src="/i.png" alt="PDF"></a></td><td>2026000011</td><td>Normal</td><td>2026</td><td>Enero</td></tr>
<tr><td><a href="/pdf/2"><img src="/i.png" alt="PDF"></a></td><td>2026000022</td><td>Normal</td><td>2026</td><td>Febrero</td></tr>
<tr><td><a href="/pdf/3"><img src="/i.png" alt="PDF"></a></td><td>2026000033</td><td>Complementaria</td><td>2026</td><td>Enero</td></tr>
<tr><td>sin icono</td><td>2026000044</td><td>Normal</td><td>2026</td><td>Marzo</td></tr>
<tr><td><a href="/pdf/5"><img src="/i.png" alt="PDF"></a></td><td>2025000055</td><td>Normal</td><td>2025</td><td>Diciembre</td></tr>
</tbody></table></body></html>"""


HOME = """<html><body><h1>Portal (simulado)</h1>
<div role="tab" id="tab" onclick="document.getElementById('panel').style.display='block'">Declara</div>
<div id="panel" style="display:none"><a href="/consulta">Pagos provisionales del ISR</a></div></body></html>"""


HEAD = '<tr><th>PDF</th><th>No. de operación</th><th>Tipo de declaración</th><th>Ejercicio</th><th>Periodo</th></tr>'


def table(*links):
    rows = ''.join(
        f'<tr><td><a href="{link}"><img src="/i.png" alt="PDF"></a></td><td>20260000{n}1</td><td>Normal</td>'
        f'<td>2026</td><td>Mes {n}</td></tr>'
        for n, link in enumerate(links, start=1)
    )
    return f'<html><body><table><thead>{HEAD}</thead><tbody>{rows}</tbody></table></body></html>'


PAGES = {
    '/expirada': table('/pdf/2', '/pdf/2', '/pdf/2', '/pdf/1', '/pdf/1'),  # every download is a login page
    '/inestable': table('/flaky'),  # the first request hangs; the retry answers at once
    '/dos': table('/pdf/1', '/pdf/3'),
    '/paginada': table('/pdf/1').replace('</body>', '<a rel="next" href="#">Siguiente</a></body>'),
}
HITS = {'flaky': 0}


class FakeSat(BaseHTTPRequestHandler):
    def log_message(self, *_):
        return

    def do_GET(self):  # noqa: N802
        if self.path == '/':
            body, kind, extra = HOME.encode(), 'text/html; charset=utf-8', {}
        elif self.path in PAGES:
            body, kind, extra = PAGES[self.path].encode(), 'text/html; charset=utf-8', {}
        elif self.path == '/flaky':
            HITS['flaky'] += 1
            if HITS['flaky'] == 1 or HITS['flaky'] < 0:
                time.sleep(3)
            body, kind = PDF + b'flaky', 'application/pdf'
            extra = {'Content-Disposition': 'attachment; filename="flaky.pdf"'}
        elif self.path == '/consulta':
            body, kind, extra = PAGE.encode(), 'text/html; charset=utf-8', {}
        elif self.path == '/pdf/2':  # a session-expired page served as if it were the PDF
            body, kind = b'<html>sesion expirada</html>', 'application/pdf'
            extra = {'Content-Disposition': 'attachment; filename="acuse.pdf"'}
        elif self.path.startswith('/pdf/'):
            body, kind = PDF + self.path.encode(), 'application/pdf'
            extra = {'Content-Disposition': f'attachment; filename="declaracion{self.path[-1]}.pdf"'}
        else:
            body, kind, extra = b'x', 'image/png', {}
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        for key, value in extra.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def fake_sat():
    server = ThreadingHTTPServer(('127.0.0.1', 0), FakeSat)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_address[1]}'
    server.shutdown()


def test_columns_are_found_by_header_with_the_original_index_as_fallback():
    heads = ['PDF', 'No. de operación', 'Tipo de declaración', 'Ejercicio', 'Periodo']
    columns = sb.column_map(heads)
    assert columns == {'operacion': 1, 'tipo': 2, 'periodo': 4, 'ejercicio': 3}
    assert sb.column_map([])['periodo'] == 6  # no headers: the original layout
    assert sb.row_entry(['', '2026000011', 'Normal', '2026', 'Enero'], columns) == ('2026000011', 'Normal', 'Enero')
    assert sb.row_entry(['solo una celda'], columns) is None


def test_consulta_is_recognized_by_its_headers_ignoring_accents():
    assert sb.is_consulta_text('No. de operación | Tipo de declaración')
    assert not sb.is_consulta_text('Inicia sesión con tu FIEL')


def test_pdf_check_and_names(tmp_path):
    (tmp_path / 'a.bin').write_bytes(PDF)
    (tmp_path / 'b.bin').write_bytes(b'<html>')
    assert sb.is_pdf_file(tmp_path / 'a.bin') and not sb.is_pdf_file(tmp_path / 'b.bin')
    assert not sb.is_pdf_file(tmp_path / 'no-existe')
    first = sb.unique_path(tmp_path, '../declaracion')  # never leaves the folder, always .pdf
    assert first == tmp_path / 'declaracion.pdf'
    first.write_bytes(PDF)
    assert sb.unique_path(tmp_path, 'declaracion.pdf').name == 'declaracion (2).pdf'


def test_without_a_configured_address_nothing_is_opened(tmp_path):
    with pytest.raises(sb.SatError) as caught:
        sb.download_all({}, tmp_path / 'staging')
    assert caught.value.code == 'sat_no_habilitado'


def run_download(base, tmp_path, **options):
    pytest.importorskip('playwright')
    progress = []
    try:
        result = sb.download_all(
            {'base_url': base, 'headless': True, 'profile_dir': tmp_path / 'profile', 'login_timeout': 20, **options},
            tmp_path / 'staging',
            on_progress=progress.append,
        )
    except sb.SatError as exc:
        if exc.code in ('sat_navegador_no_disponible', 'sat_sin_playwright'):
            pytest.skip('Firefox de Playwright no está instalado en este equipo.')
        raise
    return result, progress


def test_download_from_the_simulated_portal(fake_sat, tmp_path):
    result, progress = run_download(fake_sat + '/consulta', tmp_path)
    # Four rows have a PDF control; the fifth has none and is never clicked. The second is not a real PDF.
    assert result['detectadas'] == 4 and result['guardadas'] == 3
    assert result['fallidas'] == [
        {
            'fila': 2,
            'operacion': '2026000022',
            'tipo': 'Normal',
            'periodo': 'Febrero',
            'motivo': 'no_es_pdf',
            'intentos': 1,
        }
    ]
    names = sorted(f['nombre'] for f in result['archivos'])
    assert names == ['declaracion1.pdf', 'declaracion3.pdf', 'declaracion5.pdf']
    assert {f['periodo'] for f in result['archivos']} == {'Enero', 'Diciembre'}
    assert {f['tipo'] for f in result['archivos']} == {'Normal', 'Complementaria'}
    assert all(sb.is_pdf_file(tmp_path / 'staging' / n) for n in names)
    assert [e['fase'] for e in progress[:2]] == ['abriendo', 'esperando_sesion'] and progress[-1]['hechas'] == 4


def test_only_the_requested_fiscal_year_is_downloaded(fake_sat, tmp_path):
    result, _ = run_download(fake_sat + '/consulta', tmp_path, ejercicio=2025)
    assert result['detectadas'] == 1 and result['guardadas'] == 1 and result['fallidas'] == []
    assert [f['nombre'] for f in result['archivos']] == ['declaracion5.pdf']


def test_a_table_without_a_year_column_is_not_filtered():
    assert sb.row_year(['a', 'b'], {'tipo': 1}) == ''
    assert sb.row_year(['a', ' 2026 '], {'ejercicio': 1}) == '2026'


def test_guided_entry_follows_the_original_route_to_the_query(fake_sat, tmp_path):
    result, _ = run_download(fake_sat + '/', tmp_path, guided=True, ejercicio=2026)
    assert result['detectadas'] == 3 and result['guardadas'] == 2


def test_a_slow_download_is_retried_and_succeeds(fake_sat, tmp_path):
    HITS['flaky'] = 0
    result, _ = run_download(fake_sat + '/inestable', tmp_path, download_timeout_ms=1000, retry_pause_ms=200)
    assert result['guardadas'] == 1 and result['fallidas'] == []


def test_a_row_that_keeps_failing_is_recorded_with_its_attempts(fake_sat, tmp_path):
    HITS['flaky'] = -100  # every request hangs
    result, _ = run_download(fake_sat + '/inestable', tmp_path, download_timeout_ms=500, retries=1, retry_pause_ms=100)
    assert result['guardadas'] == 0
    assert result['fallidas'] == [
        {
            'fila': 1,
            'operacion': '202600001' + '1',
            'tipo': 'Normal',
            'periodo': 'Mes 1',
            'motivo': 'descarga_fallida',
            'intentos': 2,
        }
    ]


def test_several_non_pdf_downloads_in_a_row_stop_the_queue_as_an_expired_session(fake_sat, tmp_path):
    result, _ = run_download(fake_sat + '/expirada', tmp_path)
    assert result['interrumpida'] == 'sesion_expirada'
    assert result['guardadas'] == 0 and [f['fila'] for f in result['fallidas']] == [1, 2, 3]
    assert all(f['motivo'] == 'no_es_pdf' and f['intentos'] == 1 for f in result['fallidas'])


def test_cancelling_keeps_what_was_already_downloaded(fake_sat, tmp_path):
    pytest.importorskip('playwright')
    seen = []

    def progress(event):
        seen.append(event)

    def stop():
        return any(e.get('hechas') == 1 for e in seen)  # after the first row

    try:
        result = sb.download_all(
            {'base_url': fake_sat + '/dos', 'headless': True, 'profile_dir': tmp_path / 'p', 'login_timeout': 20},
            tmp_path / 'staging',
            on_progress=progress,
            should_stop=stop,
        )
    except sb.SatError as exc:
        if exc.code in ('sat_navegador_no_disponible', 'sat_sin_playwright'):
            pytest.skip('Firefox de Playwright no está instalado en este equipo.')
        raise
    assert result['cancelada'] is True and result['guardadas'] == 1 and result['detectadas'] == 2


def test_dry_run_describes_the_table_and_downloads_nothing(fake_sat, tmp_path):
    result, _ = run_download(fake_sat + '/consulta', tmp_path, dry_run=True)
    assert result['prueba_en_seco'] is True and result['detectadas'] == 4 and result['guardadas'] == 0
    assert result['archivos'] == [] and result['paginacion'] is False
    assert 'NO. DE OPERACION' in result['encabezados'] and result['columnas']['operacion'] == 1
    assert result['coincide_url'] is False  # the simulated address is not the SAT's
    assert not any((tmp_path / 'staging').iterdir())  # not one click, not one file


def test_dry_run_warns_when_the_table_has_more_pages(fake_sat, tmp_path):
    result, _ = run_download(fake_sat + '/paginada', tmp_path, dry_run=True)
    assert result['paginacion'] is True and result['detectadas'] == 1
