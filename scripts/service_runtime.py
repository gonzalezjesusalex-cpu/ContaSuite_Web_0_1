"""Explicit runtime for packaged installations. Never provisions configuration or schema."""

import argparse, os, sys, threading, ipaddress, json
from pathlib import Path

SERVICE_PORT = 8062  # packaged service / production
LEGACY_PORT = 8000  # INICIAR_* launchers of the old instance kept in this folder (plan, point 28)
DEV_PORT = 8090  # npm run dev; avoids the pilot (8062), local install (8072) and old instance (8000)


def default_port(fallback=SERVICE_PORT):
    """Single source for the API port: CS_PORT when set, otherwise the launcher's own default."""
    raw = os.environ.get('CS_PORT', '').strip()
    if not raw:
        return fallback
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ValueError('CS_PORT must be a port number between 1 and 65535')
    return int(raw)


def api_server(port=SERVICE_PORT, host='127.0.0.1', stop_event=None, on_ready=None, log_config=None):
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(
            'app.main:app',
            host=host,
            port=port,
            workers=1,
            proxy_headers=True,
            forwarded_allow_ips='127.0.0.1',
            log_config=log_config or uvicorn.config.LOGGING_CONFIG,
            timeout_graceful_shutdown=25,
        )
    )

    def watch():
        announced = False
        while not server.should_exit:
            if server.started and not announced:
                announced = True
                if on_ready:
                    on_ready()
            if stop_event and stop_event.wait(0.1):
                server.should_exit = True
                break
            if stop_event is None:
                break

    threading.Thread(target=watch, daemon=True).start()
    server.run()
    return bool(server.started)


def configure(data_dir):
    for name in ('DATABASE_URL', 'APP_TOKEN', 'AGENT_TOKEN'):
        if not os.environ.get(name):
            raise ValueError(name + ' must be explicitly provisioned; no dotenv fallback')
    if not data_dir.is_absolute():
        raise ValueError('Use an absolute data directory')
    os.environ.update(PYTHON_DOTENV_DISABLED='1', DATA_DIR=str(data_dir), SEED_DEMO='false')
    os.environ.setdefault('CS_STORAGE_ALLOWED_ROOTS', '[]')
    os.environ.setdefault('CS_STORAGE_SMB_ALLOWED_ROOTS', '[]')
    os.environ.setdefault('CS_ALLOWED_HOSTS', json.dumps(['127.0.0.1', 'localhost', '[::1]']))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--mode', choices=['api', 'alerts', 'index'], default='api')
    parser.add_argument('--port', type=int, default=None, help='Default: CS_PORT or 8062')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--allow-lan', action='store_true')
    args = parser.parse_args()
    if args.port is None:
        try:
            args.port = default_port()
        except ValueError as exc:
            parser.error(str(exc))
    if not 1 <= args.port <= 65535:
        parser.error('Invalid port')
    if not ipaddress.ip_address(args.host).is_loopback and (
        not args.allow_lan or os.environ.get('CS_TLS_TERMINATED') != '1'
    ):
        parser.error('Non-loopback binding requires explicit LAN/TLS configuration')
    try:
        configure(args.data_dir)
    except ValueError as exc:
        parser.error(str(exc))
    if args.mode == 'api':
        api_server(args.port, args.host)
    else:
        from app.database import engine
        from app.schema_compatibility import assert_schema

        assert_schema(engine)
        from app.storage.worker import main as worker

        sys.argv = ['worker', '--mode', args.mode]
        worker()


if __name__ == '__main__':
    main()
