"""Verificación previa de la descarga del SAT en ESTE equipo. No abre el portal, no abre el navegador ni toca datos.

Uso:  python scripts/sat_preflight.py [--config RUTA]

Lee la configuración del agente sólo para decir si trae el bloque `sat` y de qué tipo es; nunca imprime tokens,
rutas de carpetas ni direcciones completas (sólo el servidor del portal). Código de salida 0 si todo está listo.
"""

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}


def default_base():
    return Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'ContaSuite' / 'agent'


def check_config(path):
    """(lines, sat) where `sat` is the configuration block or None."""
    path = Path(path)
    if not path.exists():
        return [('FALTA', f'No existe {path.name}: el agente no tiene configuración en este equipo.')], None
    try:
        config = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return [('FALTA', f'{path.name} no se puede leer como JSON.')], None
    sat = config.get('sat') if isinstance(config, dict) else None
    if not isinstance(sat, dict) or not sat.get('base_url'):
        return [('FALTA', 'La configuración no trae `sat.base_url`: el agente no ofrecerá la descarga.')], None
    url = urlparse(str(sat['base_url']))
    lines = []
    if url.scheme != 'https' and url.hostname not in LOCAL_HOSTS:
        lines.append(('FALTA', 'La dirección del portal debe ser HTTPS (HTTP sólo en localhost).'))
    else:
        lines.append(('OK', f'Portal configurado: {url.scheme}://{url.hostname} (sólo el servidor).'))
    for flag, note in (
        ('dry_run', 'PRUEBA EN SECO: reconoce la tabla y no descarga nada.'),
        ('guided', 'Entrada guiada: pestaña «Declara» y enlace «Pagos provisionales del ISR».'),
    ):
        lines.append(('OK' if sat.get(flag) else 'INFO', f'{flag}: ' + (note if sat.get(flag) else 'desactivado.')))
    return lines, sat


def check_browser(sat):
    lines = []
    try:
        import playwright  # noqa: F401
    except ImportError:
        return [('FALTA', 'Playwright no está instalado: ejecuta INSTALAR_NAVEGADOR_SAT.bat.')]
    lines.append(('OK', 'Playwright instalado.'))
    browsers = Path((sat or {}).get('browsers_dir') or default_base() / 'playwright-browsers')
    found = sorted(browsers.glob('firefox-*')) if browsers.exists() else []
    lines.append(
        ('OK', 'Firefox del agente instalado.')
        if found
        else ('FALTA', 'Firefox del agente no está instalado: ejecuta INSTALAR_NAVEGADOR_SAT.bat.')
    )
    profile = Path((sat or {}).get('profile_dir') or default_base() / 'sat-profile')
    parent = profile if profile.exists() else profile.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    lines.append(
        ('OK', 'La carpeta del perfil del navegador se puede crear.')
        if os.access(parent, os.W_OK)
        else ('FALTA', 'No hay permiso para crear la carpeta del perfil del navegador.')
    )
    return lines


def check_agent(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            return [('OK', f'Hay un agente escuchando en 127.0.0.1:{port}.')]
    except OSError:
        return [('INFO', f'No hay un agente escuchando en 127.0.0.1:{port} (se inicia con INICIAR_AGENTE.bat).')]


def run(config_path, port=47865):
    lines, sat = check_config(config_path)
    lines += check_browser(sat)
    lines += check_agent(port)
    return lines, all(status != 'FALTA' for status, _ in lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=str(ROOT / 'agent' / 'config.json'))
    args = parser.parse_args(argv)
    lines, ready = run(args.config)
    for status, text in lines:
        print(f'[{status:5}] {text}')
    print('\nListo para la prueba.' if ready else '\nFalta algo antes de la prueba.')
    return 0 if ready else 1


if __name__ == '__main__':
    sys.exit(main())
