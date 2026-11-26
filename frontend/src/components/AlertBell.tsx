import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { alertHref, alertType, exactTime, relativeTime, severityOf } from '../alertTypes';
import { markSeen, seenAlerts, useRecentAlerts } from '../alertFeed';
import { ALERTS_PATH } from '../companyNavigation';

/** Campana de la barra superior: contador de alertas activas (rojo si hay alguna Alta) y las 5 más recientes.
 *  Al abrirla, las nuevas quedan vistas (siguen activas hasta resolverse). Se cierra con Esc o al hacer clic fuera. */
export default function AlertBell({ userId }: { userId: string }) {
  const feed = useRecentAlerts();
  const [open, setOpen] = useState(false);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const count = feed?.active_total ?? 0;
  const alerts = feed?.alerts ?? [];
  const unseen = alerts.some((a) => !seenAlerts(userId).has(a.id));
  useEffect(() => {
    if (!open) return;
    const outside = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener('mousedown', outside);
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('mousedown', outside);
      document.removeEventListener('keydown', key);
    };
  }, [open]);
  const toggle = () => {
    if (!open) {
      const seen = seenAlerts(userId);
      setFresh(new Set(alerts.filter((a) => !seen.has(a.id)).map((a) => a.id)));
      markSeen(
        userId,
        alerts.map((a) => a.id),
      );
    }
    setOpen((v) => !v);
  };
  return (
    <div className="v2-bell" ref={root}>
      <button
        ref={button}
        type="button"
        className="icon-button"
        aria-label={count ? `Alertas: ${count} activas` : 'Alertas: sin alertas activas'}
        aria-haspopup="true"
        aria-expanded={open}
        onClick={toggle}
      >
        <Bell size={17} aria-hidden />
        {count > 0 && (
          <span className={'v2-bell-count' + (feed?.active_high ? ' is-high' : '') + (unseen ? ' is-new' : '')}>
            {count > 99 ? '99+' : count}
          </span>
        )}
      </button>
      {open && (
        <div className="v2-bell-menu" role="region" aria-label="Alertas activas más recientes">
          <header>
            <strong>Alertas activas</strong>
            {count > 0 && <span className="muted">{count}</span>}
          </header>
          {alerts.length ? (
            <ul>
              {alerts.map((a) => {
                const type = alertType(a.kind);
                const severity = severityOf(a.priority);
                return (
                  <li key={a.id}>
                    <span
                      className={'v2-dot is-' + severity.tone}
                      title={'Severidad ' + severity.label.toLowerCase()}
                    />
                    <div>
                      <span className="v2-bell-text">
                        {type.text}
                        {fresh.has(a.id) && <span className="v2-new">Nuevo</span>}
                      </span>
                      <small>
                        {a.company_name} · <time title={exactTime(a.generated_at)}>{relativeTime(a.generated_at)}</time>
                      </small>
                    </div>
                    <Link className="btn small" to={alertHref(a)} onClick={() => setOpen(false)}>
                      {type.action}
                    </Link>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="v2-bell-empty muted">Sin alertas activas</p>
          )}
          <footer>
            <Link to={ALERTS_PATH} onClick={() => setOpen(false)}>
              Ver todas
            </Link>
          </footer>
        </div>
      )}
    </div>
  );
}
