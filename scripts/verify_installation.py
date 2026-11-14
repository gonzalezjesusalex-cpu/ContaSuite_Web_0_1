"""Read-only check of the definitive Windows installation (docs/INSTALACION_DEFINITIVA.md).

Runs without administrator rights, changes nothing and never prints secrets or file contents. Each
check reports OK / FALLA / PENDIENTE; the exit code is 1 if any check fails.

    python scripts/verify_installation.py [--service ContaSuiteApi] [--port 8062]
        [--private C:\\ProgramData\\ContaSuite\\private] [--url https://contasuite.despacho.local]
"""

import argparse
import json
import ssl
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
results = []


def report(name, state, detail=''):
    results.append((name, state, detail))
    print(f'[{state:9}] {name}' + (f' - {detail}' if detail else ''))


def run(command):
    done = subprocess.run(command, capture_output=True, text=True, errors='replace', creationflags=NO_WINDOW)
    return done.returncode, done.stdout


def powershell(script):
    # Inline commands are not subject to the script execution policy.
    code, out = run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script])
    return json.loads(out) if code == 0 and out.strip() else None


def as_list(value):
    return [] if value is None else value if isinstance(value, list) else [value]


def check_service(name):
    code, out = run(['sc.exe', 'qc', name])
    if code == 1060:
        report('Servicio registrado', 'FALLA', name + ' no existe')
        return
    report('Servicio registrado', 'OK' if code == 0 else 'FALLA', name)
    lines = {k.strip(): v.strip() for k, _, v in (line.partition(':') for line in out.splitlines()) if v}
    start = lines.get('START_TYPE', '')
    account = lines.get('SERVICE_START_NAME', '')
    report('Inicio automático', 'OK' if 'AUTO_START' in start else 'FALLA', start)
    report('Cuenta virtual sin privilegios', 'OK' if account == 'NT SERVICE\\' + name else 'FALLA', account)
    code, out = run(['sc.exe', 'qfailure', name])
    restarts = out.upper().count('RESTART')
    report('Recuperación tras caída', 'OK' if restarts >= 3 else 'FALLA', f'{restarts} reinicios configurados')
    code, out = run(['sc.exe', 'query', name])
    report(
        'Servicio en ejecución', 'OK' if 'RUNNING' in out else 'FALLA', 'RUNNING' if 'RUNNING' in out else 'detenido'
    )


def check_health(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=5) as response:
            body = json.loads(response.read())
        report(
            'API en loopback', 'OK' if body.get('status') == 'ok' else 'FALLA', 'versión ' + str(body.get('version'))
        )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        report('API en loopback', 'FALLA', type(exc).__name__)


def check_listeners(port):
    rows = powershell(
        'Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | '
        f'Where-Object {{ $_.LocalPort -in 5432,{port} }} | Select-Object LocalAddress,LocalPort | ConvertTo-Json'
    )
    loopback = {'127.0.0.1', '::1'}
    for wanted, label in [(port, 'API'), (5432, 'PostgreSQL')]:
        addresses = sorted({r['LocalAddress'] for r in as_list(rows) if r['LocalPort'] == wanted})
        if not addresses:
            report(f'{label} escucha sólo en loopback', 'FALLA', f'nada escucha en {wanted}')
        else:
            exposed = [a for a in addresses if a not in loopback]
            report(f'{label} escucha sólo en loopback', 'FALLA' if exposed else 'OK', ', '.join(addresses))


def check_firewall(port):
    rules = powershell(
        "Get-NetFirewallRule -Direction Inbound -Action Allow -Enabled True -ErrorAction SilentlyContinue | "
        "ForEach-Object { $p = $_ | Get-NetFirewallPortFilter; $a = $_ | Get-NetFirewallAddressFilter; "
        "[pscustomobject]@{ Name = $_.DisplayName; Ports = @($p.LocalPort); Remote = @($a.RemoteAddress); "
        "Profile = [string]$_.Profile } } | Where-Object { $_.Ports -contains '443' -or $_.Ports -contains '5432' "
        f"-or $_.Ports -contains '{port}' }} | ConvertTo-Json -Depth 3"
    )
    rules = as_list(rules)
    open_internal = [r['Name'] for r in rules if {'5432', str(port)} & set(as_list(r['Ports']))]
    report('Sin reglas entrantes para 5432 ni API', 'FALLA' if open_internal else 'OK', ', '.join(open_internal))
    # Only ContaSuite's own rule (named as in the guide); other software may legitimately use 443.
    https = [r for r in rules if '443' in as_list(r['Ports']) and r['Name'].startswith('ContaSuite')]
    if not https:
        report('Regla HTTPS 443 acotada', 'PENDIENTE', 'aún no existe (paso de HTTPS en LAN)')
    else:
        broad = [r['Name'] for r in https if 'Any' in as_list(r['Remote']) or 'Public' in r['Profile']]
        report(
            'Regla HTTPS 443 acotada', 'FALLA' if broad else 'OK', ', '.join(broad) or 'subred y perfil restringidos'
        )


def check_private(folder):
    folder = Path(folder)
    if not folder.is_dir():
        report('Configuración privada protegida', 'FALLA', f'no existe {folder}')
        return
    code, out = run(['icacls', str(folder)])
    broad = [g for g in ('Everyone', 'Todos', 'BUILTIN\\Users', 'BUILTIN\\Usuarios', 'Authenticated Users') if g in out]
    report(
        'Configuración privada protegida', 'FALLA' if code or broad else 'OK', ', '.join(broad) or 'sin grupos amplios'
    )


def check_https(url):
    try:
        context = ssl.create_default_context()
        context.load_default_certs()
        with urllib.request.urlopen(url.rstrip('/') + '/api/health', timeout=8, context=context) as response:
            hsts = response.headers.get('Strict-Transport-Security')
            report('HTTPS con certificado de confianza', 'OK', 'HSTS ' + ('sí' if hsts else 'no'))
    except ssl.SSLError as exc:
        report('HTTPS con certificado de confianza', 'FALLA', 'certificado: ' + exc.reason if exc.reason else 'TLS')
    except (urllib.error.URLError, OSError) as exc:
        report('HTTPS con certificado de confianza', 'FALLA', type(exc).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--service', default='ContaSuiteApi')
    parser.add_argument('--port', type=int, default=8062)
    parser.add_argument('--private', default=r'C:\ProgramData\ContaSuite\private')
    parser.add_argument('--url', help='Dirección HTTPS de la LAN (omitir hasta configurar Nginx)')
    args = parser.parse_args()
    check_service(args.service)
    check_health(args.port)
    check_listeners(args.port)
    check_firewall(args.port)
    check_private(args.private)
    if args.url:
        check_https(args.url)
    else:
        report('HTTPS con certificado de confianza', 'PENDIENTE', 'pasar --url cuando exista')
    failed = sum(1 for _, state, _ in results if state == 'FALLA')
    print(
        f'\n{len(results)} comprobaciones: {failed} fallan, '
        f'{sum(1 for _, s, _ in results if s == "PENDIENTE")} pendientes.'
    )
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
