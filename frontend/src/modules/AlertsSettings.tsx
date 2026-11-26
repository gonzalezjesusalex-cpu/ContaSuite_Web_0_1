import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Copy, FolderOpen, Search, Timer, XCircle } from 'lucide-react';
import { api } from '../api';
import { Empty, Field, Modal } from '../components/ui';
import { stitchButton, stitchPrimary } from '../components/stitch';
import { MoreMenu } from './CompanyHeader';
import { alertHref, alertType, dossierHref, exactTime, relativeTime, SEVERITY, severityOf } from '../alertTypes';
import { alertsChanged, feedPath, type Feed, type FeedAlert } from '../alertFeed';
import type { State } from '../types';

const PAGE = 10;
const STATE_TEXT: Record<FeedAlert['state'], string> = {
  active: 'Activa',
  snoozed: 'Pospuesta',
  resolved: 'Resuelta',
  obsolete: 'Resuelta',
  dismissed: 'Descartada',
};
const day = (iso: string) => new Date(iso + 'T12:00:00').toLocaleDateString('es-MX');
const tomorrow = () => new Date(Date.now() + 86400000).toISOString().slice(0, 10);

/** Configuración › Alertas: pendientes detectados en expedientes y documentos, como registro de eventos (la más
 *  reciente arriba). Activas e Historial; el código interno y el identificador nunca se muestran en la fila. */
export default function AlertsSettings({ state, notify }: { state: State; notify: (m: string) => void }) {
  const [params, setParams] = useSearchParams();
  const view = params.get('sub') === 'historial' ? 'history' : 'active';
  const [severity, setSeverity] = useState('');
  const [kind, setKind] = useState('');
  const [company, setCompany] = useState('');
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const [feed, setFeed] = useState<Feed | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  const [snoozing, setSnoozing] = useState<FeedAlert | null>(null);
  const [dismissing, setDismissing] = useState<FeedAlert | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(() => setQ(text.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [text]);
  useEffect(() => setPage(0), [view, severity, kind, company, q]);
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setError('');
    api<Feed>(
      feedPath({ view, offset: page * PAGE, limit: PAGE, severity, kind, company_id: company, q }),
      'GET',
      undefined,
      abort.signal,
    )
      .then(setFeed)
      .catch((e) => !abort.signal.aborted && setError(e.message))
      .finally(() => !abort.signal.aborted && setLoading(false));
    return () => abort.abort();
  }, [view, page, severity, kind, company, q, reload]);
  const changed = () => {
    setReload((n) => n + 1);
    alertsChanged();
  };
  async function act(alert: FeedAlert, body: { state: string; reason: string; snooze_until?: string }) {
    await api('/integral/alerts/' + alert.id + '/lifecycle', 'PUT', { revision: alert.revision, ...body });
    changed();
  }
  async function copyId(alert: FeedAlert) {
    try {
      await navigator.clipboard.writeText(alert.id);
      notify('ID de la alerta copiado');
    } catch {
      notify('No se pudo copiar el ID');
    }
  }
  const alerts = feed?.alerts || [];
  const total = feed?.total || 0;
  const from = total ? page * PAGE + 1 : 0;
  const to = Math.min(total, (page + 1) * PAGE);
  const filtered = !!(severity || kind || company || q);
  const actionable = (a: FeedAlert) => !!feed?.lifecycle_available && a.revision !== null;
  return (
    <section id="cfg-alertas" className="card padded v2-alerts">
      <h2>Alertas{feed ? ` (${feed.active_total})` : ''}</h2>
      <p className="muted">Pendientes detectados en expedientes y documentos de tus empresas.</p>
      <nav className="tabs card subtabs" aria-label="Subpestañas de Alertas">
        {(
          [
            ['activas', 'Activas', 'active'],
            ['historial', 'Historial', 'history'],
          ] as const
        ).map(([id, label, v]) => (
          <Link
            key={id}
            to={'/configuracion/alertas?sub=' + id}
            className={view === v ? 'active' : ''}
            aria-current={view === v ? 'page' : undefined}
            onClick={(e) => {
              e.preventDefault();
              setParams({ sub: id });
            }}
          >
            {label}
          </Link>
        ))}
      </nav>
      <div className="toolbar" role="group" aria-label="Filtros de alertas">
        <select aria-label="Severidad" value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="">Todas las severidades</option>
          {(['high', 'medium', 'low'] as const).map((s) => (
            <option key={s} value={s}>
              {SEVERITY[s].label}
            </option>
          ))}
        </select>
        <select aria-label="Tipo de alerta" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">Todos los tipos</option>
          {[...new Set([...(feed?.kinds || []), ...(kind ? [kind] : [])])]
            .map((k) => [k, alertType(k).text] as const)
            .sort((a, b) => a[1].localeCompare(b[1], 'es'))
            .map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
        </select>
        <select aria-label="Empresa" value={company} onChange={(e) => setCompany(e.target.value)}>
          <option value="">Todas las empresas</option>
          {state.companies
            .filter((c) => !c.archived)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
        </select>
        <div className="search-field">
          <Search size={17} aria-hidden />
          <input
            type="search"
            aria-label="Buscar en alertas"
            placeholder="Buscar por empresa o documento…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
      </div>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {loading && !feed && <p role="status">Consultando alertas…</p>}
      {feed && !feed.lifecycle_available && (
        <p className="info-box">
          El seguimiento de alertas (posponer, descartar e historial) está pendiente de su migración autorizada.
        </p>
      )}
      {feed &&
        (alerts.length ? (
          <div className="table-wrap" aria-busy={loading}>
            <table className="v2-alerts-table">
              <thead>
                <tr>
                  <th scope="col">Severidad</th>
                  <th scope="col">Alerta</th>
                  <th scope="col">Empresa</th>
                  <th scope="col">Detalle</th>
                  {view === 'active' ? (
                    <>
                      <th scope="col">Detectada</th>
                      <th scope="col">Acción</th>
                    </>
                  ) : (
                    <>
                      <th scope="col">Estado</th>
                      <th scope="col">Usuario</th>
                      <th scope="col">Fecha</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => {
                  const type = alertType(a.kind);
                  const sev = severityOf(a.priority);
                  return (
                    <tr key={a.id}>
                      <td>
                        <span className="v2-severity">
                          <span className={'v2-dot is-' + sev.tone} aria-hidden />
                          {sev.label}
                        </span>
                      </td>
                      <td>{type.text}</td>
                      <td>
                        <Link to={dossierHref(a)}>{a.company_name}</Link>
                      </td>
                      <td className="muted">{a.detail || '—'}</td>
                      {view === 'active' ? (
                        <>
                          <td>
                            <time title={exactTime(a.generated_at)}>{relativeTime(a.generated_at)}</time>
                          </td>
                          <td>
                            <div className="v2-alert-actions">
                              <Link className={stitchButton} to={alertHref(a)}>
                                {type.action}
                              </Link>
                              <MoreMenu label={'Más acciones: ' + type.text + ', ' + a.company_name}>
                                <Link role="menuitem" to={dossierHref(a)}>
                                  <FolderOpen size={16} /> Abrir expediente
                                </Link>
                                <button role="menuitem" type="button" onClick={() => void copyId(a)}>
                                  <Copy size={16} /> Copiar ID
                                </button>
                                <button
                                  role="menuitem"
                                  type="button"
                                  disabled={!actionable(a)}
                                  onClick={() => setSnoozing(a)}
                                >
                                  <Timer size={16} /> Posponer
                                </button>
                                <button
                                  role="menuitem"
                                  type="button"
                                  disabled={!actionable(a)}
                                  onClick={() => setDismissing(a)}
                                >
                                  <XCircle size={16} /> Descartar
                                </button>
                              </MoreMenu>
                            </div>
                          </td>
                        </>
                      ) : (
                        <>
                          <td>
                            {STATE_TEXT[a.state]}
                            {a.state === 'snoozed' && a.snooze_until && ` hasta ${day(a.snooze_until)}`}
                            {a.reason && <small className="v2-reason">{a.reason}</small>}
                          </td>
                          <td>{a.changed_by || '—'}</td>
                          <td>
                            <time title={exactTime(a.changed_at)}>{relativeTime(a.changed_at)}</time>
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title={
              filtered
                ? 'Sin alertas en este filtro'
                : view === 'active'
                  ? 'Sin alertas activas. Todo en orden.'
                  : 'Sin alertas en el historial'
            }
          >
            {filtered ? 'Ajusta los filtros.' : undefined}
          </Empty>
        ))}
      {total > 0 && (
        <div className="table-footer">
          <span>
            Mostrando {from}–{to} de {total}
          </span>
          <div className="pagination">
            <button aria-label="Página anterior" disabled={page === 0 || loading} onClick={() => setPage((n) => n - 1)}>
              ‹
            </button>
            <button
              aria-label="Página siguiente"
              disabled={to >= total || loading}
              onClick={() => setPage((n) => n + 1)}
            >
              ›
            </button>
          </div>
        </div>
      )}
      {snoozing && <SnoozeDialog alert={snoozing} onClose={() => setSnoozing(null)} onSave={act} />}
      {dismissing && <DismissDialog alert={dismissing} onClose={() => setDismissing(null)} onSave={act} />}
    </section>
  );
}

type Save = (a: FeedAlert, body: { state: string; reason: string; snooze_until?: string }) => Promise<void>;

function SnoozeDialog({ alert, onClose, onSave }: { alert: FeedAlert; onClose: () => void; onSave: Save }) {
  const [until, setUntil] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await onSave(alert, { state: 'snoozed', snooze_until: until, reason: 'Pospuesta hasta ' + until });
      onClose();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  return (
    <Modal title="Posponer alerta" onClose={() => !busy && onClose()}>
      <form className="padded" onSubmit={submit}>
        <p>
          {alertType(alert.kind).text} · {alert.company_name}. Se oculta de Activas hasta esa fecha y luego vuelve.
        </p>
        <Field label="Posponer hasta">
          <input type="date" required min={tomorrow()} value={until} onChange={(e) => setUntil(e.target.value)} />
        </Field>
        {error && <p role="alert">{error}</p>}
        <div className="actions">
          <button type="button" className={stitchButton} disabled={busy} onClick={onClose}>
            Cancelar
          </button>
          <button className={stitchPrimary} disabled={busy || !until}>
            Posponer
          </button>
        </div>
      </form>
    </Modal>
  );
}

function DismissDialog({ alert, onClose, onSave }: { alert: FeedAlert; onClose: () => void; onSave: Save }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const valid = reason.trim().length >= 3;
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError('');
    try {
      await onSave(alert, { state: 'dismissed', reason: reason.trim() });
      onClose();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  return (
    <Modal title="Descartar alerta" onClose={() => !busy && onClose()}>
      <form className="padded" onSubmit={submit}>
        <p>
          {alertType(alert.kind).text} · {alert.company_name}. Pasa al historial como descartada.
        </p>
        <Field label="Motivo (obligatorio)">
          <input
            required
            minLength={3}
            maxLength={200}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Ej. empresa en proceso de baja"
          />
        </Field>
        {error && <p role="alert">{error}</p>}
        <div className="actions">
          <button type="button" className={stitchButton} disabled={busy} onClick={onClose}>
            Cancelar
          </button>
          <button className={stitchPrimary} disabled={busy || !valid}>
            Descartar
          </button>
        </div>
      </form>
    </Modal>
  );
}
