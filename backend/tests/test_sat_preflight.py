"""Verificación previa de la descarga del SAT: sólo lee la configuración y el equipo, nunca el portal."""

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('sat_preflight', Path(__file__).parents[2] / 'scripts/sat_preflight.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def statuses(lines):
    return {status for status, _ in lines}


def test_without_a_sat_block_the_download_is_not_offered(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'api_url': 'http://127.0.0.1:8099', 'token': 'S' * 40}), encoding='utf-8')
    lines, sat = preflight.check_config(config)
    assert sat is None and statuses(lines) == {'FALTA'}
    missing, _ = preflight.check_config(tmp_path / 'no-existe.json')
    assert statuses(missing) == {'FALTA'}
    broken = tmp_path / 'roto.json'
    broken.write_text('{no es json', encoding='utf-8')
    assert statuses(preflight.check_config(broken)[0]) == {'FALTA'}


def test_the_report_never_prints_secrets_or_the_full_address(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(
        json.dumps(
            {
                'token': 'SECRETO-DEL-AGENTE-1234567890',
                'sat': {'base_url': 'https://www.sat.gob.mx/portal/public/x?sesion=ABC123', 'dry_run': True},
            }
        ),
        encoding='utf-8',
    )
    lines, sat = preflight.check_config(config)
    text = ' '.join(t for _, t in lines)
    assert 'FALTA' not in statuses(lines) and sat['dry_run'] is True
    assert 'www.sat.gob.mx' in text and 'SECRETO' not in text and 'ABC123' not in text and '/portal' not in text
    assert 'PRUEBA EN SECO' in text


def test_a_portal_address_must_be_https_except_on_localhost(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'sat': {'base_url': 'http://www.sat.gob.mx/x'}}), encoding='utf-8')
    assert 'FALTA' in statuses(preflight.check_config(config)[0])
    config.write_text(json.dumps({'sat': {'base_url': 'http://127.0.0.1:9000/consulta'}}), encoding='utf-8')
    assert 'FALTA' not in statuses(preflight.check_config(config)[0])


def test_browser_check_reports_what_is_missing(tmp_path):
    sat = {'browsers_dir': str(tmp_path / 'sin-firefox'), 'profile_dir': str(tmp_path / 'perfil')}
    lines = preflight.check_browser(sat)
    assert any(s == 'FALTA' and 'Firefox' in t for s, t in lines) or any('Playwright' in t for _, t in lines)
    (tmp_path / 'con-firefox' / 'firefox-1572').mkdir(parents=True)
    ok = preflight.check_browser({'browsers_dir': str(tmp_path / 'con-firefox'), 'profile_dir': str(tmp_path / 'p')})
    assert ('OK', 'La carpeta del perfil del navegador se puede crear.') in ok or any('Playwright' in t for _, t in ok)
