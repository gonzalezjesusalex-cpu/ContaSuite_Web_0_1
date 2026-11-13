"""Independent alert/index modes. Never starts from HTTP."""

import argparse
import time
from uuid import uuid4


def run_once(mode, indexer=None, alert_job=None, owner='worker'):
    if mode in ('alerts', 'both'):
        if alert_job is None:
            raise ValueError('Alert executor required')
        alert_job()
    if mode in ('index', 'both'):
        if indexer is None:
            raise ValueError('Indexer required')
        indexer.tick(owner)
        job = indexer.claim(owner)
        if job:
            indexer.run(job, owner)


def main(stop_event=None, argv=None):
    parser = argparse.ArgumentParser(description='Trabajador ContaSuite con controles independientes')
    parser.add_argument('--mode', choices=['alerts', 'index', 'both'], default='index')
    parser.add_argument('--evaluate-alerts', action='store_true', help='Alias seguro: solo alertas')
    parser.add_argument('--alert-interval', type=int, default=900)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args(argv)
    if args.alert_interval < 60:
        parser.error('Intervalo mínimo: 60 segundos')
    mode = 'alerts' if args.evaluate_alerts else args.mode
    from ..database import SessionLocal

    indexer = None
    if mode in ('index', 'both'):
        from ..database import DATA
        from .settings import StorageSettings
        from .service import StorageService
        from .indexer import LocalIndexer

        indexer = LocalIndexer(StorageService(SessionLocal, StorageSettings.from_environment(DATA)))

    from ..security_retention import DailyPurge

    purge = DailyPurge(SessionLocal)

    def alert_job():
        from ..alert_schedule import tick

        with SessionLocal.begin() as db:
            result = tick(db, interval=args.alert_interval)
        try:
            purge()
        except Exception as exc:  # noqa: BLE001  A retention problem is reported but must not stop alerts.
            print('Retención de eventos de seguridad no aplicada:', type(exc).__name__, exc, flush=True)
        return result

    owner = 'worker-' + str(uuid4())
    while stop_event is None or not stop_event.is_set():
        try:
            run_once(mode, indexer, alert_job, owner)
        except Exception:
            print('Trabajo interrumpido; transacción revertida, reintento pendiente.', flush=True)
            if args.once:
                raise
        if args.once:
            return
        if stop_event is not None:
            stop_event.wait(3)
        else:
            time.sleep(3)


if __name__ == '__main__':
    main()
