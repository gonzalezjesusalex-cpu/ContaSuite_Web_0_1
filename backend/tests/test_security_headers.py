"""Security headers: strict policy on the HTML/static responses, same-origin framing for /api previews."""

from test_api import client, A  # noqa: F401  Isolated environment before app imports.
from app.main import CONTENT_SECURITY_POLICY


def assert_page_headers(response):
    assert response.headers['Content-Security-Policy'] == CONTENT_SECURITY_POLICY
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['Referrer-Policy'] == 'same-origin'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert 'camera=()' in response.headers['Permissions-Policy']


def test_policy_allows_only_own_resources():
    directives = dict(d.split(' ', 1) for d in CONTENT_SECURITY_POLICY.split('; '))
    assert directives['script-src'] == "'self'"
    assert "'unsafe-inline'" not in CONTENT_SECURITY_POLICY and "'unsafe-eval'" not in CONTENT_SECURITY_POLICY
    assert directives['frame-ancestors'] == "'none'" and directives['object-src'] == "'none'"
    assert directives['frame-src'] == "'self' blob:"


def test_html_routes_and_static_files_carry_page_headers(client):
    for path in ('/', '/empresas', '/empresas/demo?tab=Documentos', '/icons/original/claro/64/CS_ContaSuite.png'):
        assert_page_headers(client.get(path))


def test_api_keeps_same_origin_framing_for_previews(client):
    response = client.get('/api/state', headers=A)
    assert response.status_code == 200
    assert response.headers['X-Frame-Options'] == 'SAMEORIGIN'
    assert response.headers['Referrer-Policy'] == 'same-origin'
    assert response.headers['Cache-Control'] == 'private, no-store'
    assert 'Content-Security-Policy' not in response.headers
    denied = client.get('/api/state')
    assert denied.status_code == 401 and denied.headers['X-Frame-Options'] == 'SAMEORIGIN'
