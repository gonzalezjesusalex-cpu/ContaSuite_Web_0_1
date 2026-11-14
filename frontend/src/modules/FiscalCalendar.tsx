import './calendar-view.css';
import CalendarManagement from './CalendarManagement';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { api, today } from '../api';
import { Kpi } from '../components/ui';
import { canAnywhere } from '../permissions';
import type { State, Task } from '../types';

type Event = {
  id: string;
  company_id: string;
  date: string;
  title: string;
  kind: string;
  state: string;
  source: string;
  reference: string;
  href: string;
};
type Data = {
  events: Event[];
  count: number;
  start: string;
  end: string;
  sources: Record<string, boolean>;
  archive_available: boolean;
};
/** One line of the agenda: a registered fiscal date or a task with a due date. */
type Item = {
  id: string;
  date: string;
  title: string;
  company_id: string;
  detail: string;
  urgent: boolean;
  href: string;
};

// Event states as returned by the server (obligations and certificates), shown in Spanish.
const STATES: Record<string, string> = {
  pending: 'Pendiente',
  in_progress: 'En proceso',
  unreviewed: 'Sin revisar',
  overdue: 'Vencida (fecha verificada)',
  fulfilled: 'Cumplida registrada',
  not_applicable: 'No aplica',
  valid: 'Certificado vigente',
  expiring: 'Certificado por vencer',
  expired: 'Certificado vencido',
  pending_verification: 'Certificado aún no vigente',
};
const iso = (d: Date) =>
  d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
const plusDays = (day: string, n: number) => {
  const d = new Date(day + 'T12:00:00');
  d.setDate(d.getDate() + n);
  return iso(d);
};
const longDate = (day: string) =>
  new Date(day + 'T12:00:00').toLocaleDateString('es-MX', { weekday: 'long', day: 'numeric', month: 'long' });

export default function FiscalCalendar({
  state,
  period,
  onCreateTask,
}: {
  state: State;
  period: string;
  /** Opens the task form with the chosen day (Bloque 5). */
  onCreateTask?: (day: string) => void;
}) {
  const me = state.current_user;
  const [updates, setUpdates] = useState(0);
  useEffect(() => {
    const changed = () => setUpdates((n) => n + 1);
    window.addEventListener('contasuite-data-changed', changed);
    return () => window.removeEventListener('contasuite-data-changed', changed);
  }, []);
  const [anchor, setAnchor] = useState(period + '-01');
  useEffect(() => setAnchor(period + '-01'), [period]);
  const [view, setView] = useState<'month' | 'week'>('month'),
    [company, setCompany] = useState(''),
    [kind, setKind] = useState(''),
    [status, setStatus] = useState(''),
    [archived, setArchived] = useState(false),
    [mine, setMine] = useState(false),
    [selected, setSelected] = useState<string | null>(null),
    [data, setData] = useState<Data | null>(null),
    [upcoming, setUpcoming] = useState<Data | null>(null),
    [error, setError] = useState('');
  function move(delta: number) {
    const d = new Date(anchor + 'T12:00:00');
    if (view === 'month') {
      d.setDate(1);
      d.setMonth(d.getMonth() + delta);
    } else d.setDate(d.getDate() + delta * 7);
    setAnchor(iso(d));
    setSelected(null);
  }
  // «Mis pendientes» (accountants): the companies the user is responsible for (Bloque 2).
  const myCompanies = useMemo(
    () => new Set(state.companies.filter((c) => c.accountant_id === me.id).map((c) => c.id)),
    [state.companies, me.id],
  );
  const visibleCompany = (id: string) => {
    const c = state.companies.find((x) => x.id === id);
    return !!c && (archived || !c.archived) && (!company || id === company) && (!mine || myCompanies.has(id));
  };
  useEffect(() => {
    const abort = new AbortController();
    setData(null);
    setError('');
    const base = (a: string, v: string) => {
      const q = new URLSearchParams({ anchor: a, view: v, include_archived: String(archived) });
      if (company) q.set('company_id', company);
      if (kind && kind !== 'task') q.set('kind', kind);
      if (status) q.set('state', status);
      return '/integral/calendar?' + q;
    };
    Promise.all([
      api<Data>(base(anchor, view), 'GET', undefined, abort.signal),
      api<Data>(base(today(), 'upcoming'), 'GET', undefined, abort.signal),
    ])
      .then(([visible, next]) => {
        setData(visible);
        setUpcoming(next);
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, [anchor, view, company, kind, status, archived, updates]);

  const name = (id: string) => state.companies.find((c) => c.id === id)?.name || 'Empresa';
  const fromEvents = (events: Event[]): Item[] =>
    kind === 'task'
      ? []
      : events
          .filter((e) => visibleCompany(e.company_id))
          .map((e) => ({
            id: 'e' + e.id,
            date: e.date,
            title: e.title,
            company_id: e.company_id,
            detail: (STATES[e.state] || e.state) + ' · ' + e.source,
            urgent: e.state === 'overdue' || e.state === 'expired',
            href: e.href,
          }));
  const openTasks = (t: Task) => t.status !== 'Completada';
  const tasksIn = (start: string, end: string): Item[] =>
    (kind && kind !== 'task') || status
      ? []
      : state.tasks
          .filter((t) => t.due_date >= start && t.due_date <= end && visibleCompany(t.company_id))
          .map((t) => ({
            id: 't' + t.id,
            date: t.due_date,
            title: t.title,
            company_id: t.company_id,
            detail: 'Tarea · ' + t.status + (t.responsible ? ' · ' + t.responsible : ''),
            urgent: openTasks(t) && t.due_date < today(),
            href: '/tareas?tab=tareas',
          }));
  const items = data ? [...fromEvents(data.events), ...tasksIn(data.start, data.end)] : [];
  items.sort((a, b) => a.date.localeCompare(b.date) || a.title.localeCompare(b.title, 'es'));
  const next30 = upcoming ? [...fromEvents(upcoming.events), ...tasksIn(upcoming.start, upcoming.end)] : [];
  const day0 = today();
  const week = plusDays(day0, 6);
  const overdueTasks = state.tasks.filter((t) => openTasks(t) && t.due_date < day0 && visibleCompany(t.company_id));
  const overdueEvents = data ? fromEvents(data.events).filter((i) => i.urgent) : [];
  const agenda = selected ? items.filter((i) => i.date === selected) : items.filter((i) => i.date >= day0);
  const canCreate = !!onCreateTask && canAnywhere(me, 'tareas.editar');
  const days = useMemo(() => {
    if (!data) return [];
    const out: string[] = [];
    for (let d = data.start; d <= data.end; d = plusDays(d, 1)) out.push(d);
    return out;
  }, [data]);

  return (
    <>
      {/* Summaries of this tab: today, this week, overdue, next 30 days (Bloque 5). */}
      <div className="kpi-grid four">
        <Kpi label="Hoy" value={next30.filter((i) => i.date === day0).length} detail="Fechas y tareas del día" />
        <Kpi
          label="Vencen esta semana"
          value={next30.filter((i) => i.date <= week).length}
          detail="Próximos 7 días"
          tone="blue"
        />
        <Kpi
          label="Vencidas"
          value={overdueTasks.length + overdueEvents.length}
          detail="Tareas abiertas y fechas del periodo visible"
          tone="red"
        />
        <Kpi label="Próximos 30 días" value={next30.length} detail="Fechas registradas y tareas" tone="green" />
      </div>
      <details className="card padded calendar-manage-toggle">
        <summary>Gestionar fechas (manuales y reglas revisadas)</summary>
        <CalendarManagement state={state} />
      </details>
      <section className="card padded stitch-live-module">
        <h2>Calendario fiscal</h2>
        <p className="muted">
          Sin reglas legales inferidas: sólo fechas registradas y tareas con fecha límite. Incluye certificados
          históricos; la selección actual se gestiona en Certificados.
        </p>
        <div className="toolbar calendar-controls">
          <button className="btn" onClick={() => move(-1)} aria-label="Periodo anterior">
            Anterior
          </button>
          <button className="btn" onClick={() => move(1)} aria-label="Periodo siguiente">
            Siguiente
          </button>
          <input
            type="date"
            aria-label="Día de corte del calendario"
            value={anchor}
            onChange={(e) => {
              if (e.target.value) {
                setAnchor(e.target.value);
                setSelected(null);
              }
            }}
          />
          <select
            aria-label="Vista del calendario"
            value={view}
            onChange={(e) => setView(e.target.value as 'month' | 'week')}
          >
            <option value="month">Mes</option>
            <option value="week">Semana</option>
          </select>
          <select aria-label="Empresa del calendario" value={company} onChange={(e) => setCompany(e.target.value)}>
            <option value="">Todas las autorizadas</option>
            {state.companies
              .filter((c) => archived || !c.archived)
              .map((c) => (
                <option value={c.id} key={c.id}>
                  {c.name}
                </option>
              ))}
          </select>
          <select aria-label="Tipo de evento" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">Todos los tipos</option>
            <option value="obligation">Obligación</option>
            <option value="certificate">Certificado</option>
            <option value="manual">Fecha manual / regla revisada</option>
            <option value="task">Tarea</option>
          </select>
          <select aria-label="Estado del evento" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Todos los estados</option>
            {Object.entries(STATES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          {me.role === 'contador' && (
            <button
              type="button"
              role="switch"
              aria-checked={mine}
              className={'switch' + (mine ? ' on' : '')}
              onClick={() => setMine((v) => !v)}
            >
              <span aria-hidden="true" />
              Mis pendientes
            </button>
          )}
          <button
            type="button"
            role="switch"
            aria-checked={archived}
            className={'switch' + (archived ? ' on' : '')}
            onClick={() => setArchived((v) => !v)}
          >
            <span aria-hidden="true" />
            Incluir archivadas
          </button>
        </div>
        {error ? (
          <p role="alert">{error}</p>
        ) : !data ? (
          <p role="status">Consultando fechas…</p>
        ) : (
          <>
            <p className="muted">
              {data.start} — {data.end} · {items.length} fechas y tareas · hora de México · obligaciones{' '}
              {data.sources.obligations ? 'disponibles' : 'no activadas'}, certificados{' '}
              {data.sources.certificates ? 'disponibles' : 'no activados'}.
              {!data.archive_available && ' Esquema de archivo no disponible; exclusión por archivo no evaluable.'}
            </p>
            <div className="calendar-layout">
              <div
                className={'calendar-grid ' + (view === 'week' ? 'calendar-week' : 'calendar-month')}
                role="group"
                aria-label={view === 'week' ? 'Semana' : 'Mes'}
              >
                {days.map((day, i) => {
                  const dayItems = items.filter((x) => x.date === day);
                  return (
                    <button
                      type="button"
                      className={
                        'calendar-day' + (day === selected ? ' selected' : '') + (day === day0 ? ' today' : '')
                      }
                      aria-pressed={day === selected}
                      aria-label={longDate(day) + ': ' + dayItems.length + ' fechas y tareas'}
                      key={day}
                      onClick={() => setSelected(day === selected ? null : day)}
                      style={
                        view === 'month' && i === 0
                          ? { gridColumnStart: ((new Date(day + 'T12:00:00').getDay() + 6) % 7) + 1 }
                          : undefined
                      }
                    >
                      <time dateTime={day}>
                        {new Date(day + 'T12:00:00').toLocaleDateString('es-MX', {
                          weekday: 'short',
                          day: 'numeric',
                        })}
                      </time>
                      {dayItems.slice(0, 3).map((x) => (
                        <span key={x.id} className={'calendar-event' + (x.urgent ? ' calendar-urgent' : '')}>
                          {x.title}
                        </span>
                      ))}
                      {dayItems.length > 3 && <small>+{dayItems.length - 3} más</small>}
                    </button>
                  );
                })}
              </div>
              <aside className="calendar-agenda" aria-label="Agenda">
                <div className="calendar-agenda-head">
                  <h3>{selected ? longDate(selected) : 'Próximas fechas'}</h3>
                  {selected && (
                    <button type="button" className="link-button" onClick={() => setSelected(null)}>
                      Ver todas
                    </button>
                  )}
                </div>
                {selected && canCreate && (
                  <button type="button" className="btn" onClick={() => onCreateTask!(selected)}>
                    <Plus size={16} />
                    Nueva tarea para este día
                  </button>
                )}
                {agenda.length === 0 ? (
                  <p className="muted">
                    {selected ? 'Sin fechas ni tareas este día.' : 'Sin fechas próximas en el periodo visible.'} No
                    acredita cumplimiento.
                  </p>
                ) : (
                  <ol>
                    {agenda.map((x) => (
                      <li key={x.id} className={x.urgent ? 'calendar-urgent' : undefined}>
                        {!selected && <time dateTime={x.date}>{x.date}</time>}
                        <Link to={x.href}>{x.title}</Link>
                        <small>
                          {name(x.company_id)} · {x.detail}
                        </small>
                      </li>
                    ))}
                  </ol>
                )}
              </aside>
            </div>
          </>
        )}
      </section>
    </>
  );
}
