"""Fase 1 del navegador del agente: lógica pura y descarga contra un SAT simulado (sin tocar el portal real)."""

import sys
import threading
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
</tbody></table></body></html>"""


class FakeSat(BaseHTTPRequestHandler):
    def log_message(self, *_):
        return

    def do_GET(self):  # noqa: N802
        if self.path == '/consulta':
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
    yield f'http://127.0.0.1:{server.server_address[1]}/consulta'
    server.shutdown()


def test_columns_are_found_by_header_with_the_original_index_as_fallback():
    heads = ['PDF', 'No. de operación', 'Tipo de declaración', 'Ejercicio', 'Periodo']
    columns = sb.column_map(heads)
    assert columns == {'operacion': 1, 'tipo': 2, 'periodo': 4}
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


def test_download_from_the_simulated_portal(fake_sat, tmp_path):
    pytest.importorskip('playwright')
    progress = []
    try:
        result = sb.download_all(
            {'base_url': fake_sat, 'headless': True, 'profile_dir': tmp_path / 'profile', 'login_timeout': 20},
            tmp_path / 'staging',
            on_progress=progress.append,
        )
    except sb.SatError as exc:
        if exc.code in ('sat_navegador_no_disponible', 'sat_sin_playwright'):
            pytest.skip('Firefox de Playwright no está instalado en este equipo.')
        raise
    # Three rows have a PDF control; the fourth has none and is never clicked.
    assert result['detectadas'] == 3 and result['guardadas'] == 2
    assert result['errores'] == [{'fila': 2, 'motivo': 'no_es_pdf'}]
    names = sorted(f['nombre'] for f in result['archivos'])
    assert names == ['declaracion1.pdf', 'declaracion3.pdf']
    assert {f['periodo'] for f in result['archivos']} == {'Enero'}
    assert {f['tipo'] for f in result['archivos']} == {'Normal', 'Complementaria'}
    assert all(sb.is_pdf_file(tmp_path / 'staging' / n) for n in names)
    assert progress[0]['fase'] == 'esperando_sesion' and progress[-1]['hechas'] == 3
