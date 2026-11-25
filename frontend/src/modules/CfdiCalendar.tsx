import { useEffect, useState } from 'react';
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  MinusCircle,
  RefreshCw,
} from 'lucide-react';
import { api, download } from '../api';
import { Modal } from '../components/ui';
import { stitchButton, stitchPrimary } from '../components/stitch';
import './v11.css';

type Side = { count: number; total: number };
type Cell = { issued: Side; received: Side };
type YearData = {
  company: { id: string; name: string; rfc: string };
  year: number;
  months: (Cell & { month: number })[];
  month?: number;
  days?: (Cell & { day: number })[];
  indexed: number;
};
type Row = {
  document_id: string;
  name: string;
  uuid: string | null;
  counterpart_rfc: string;
  type: string;
  total: number;
  currency: string | null;
  stamped_on: string | null;
};
const MONTHS = [
  'Enero',
  'Febrero',
  'Marzo',
  'Abril',
  'Mayo',
  'Junio',
  'Julio',
  'Agosto',
  'Septiembre',
  'Octubre',
  'Noviembre',
  'Diciembre',
];
const WEEKDAYS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
const money = (n: number) => n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN' });

function state(c: Cell) {
  const i = c.issued.count > 0,
    r = c.received.count > 0;
  return i && r ? 'cfdi-both' : i ? 'cfdi-issued' : r ? 'cfdi-received' : 'cfdi-none';
}
function stateText(c: Cell) {
  const s = state(c);
  return s === 'cfdi-both'
    ? 'Emitidas y recibidas'
    : s === 'cfdi-issued'
      ? 'Sólo emitidas'
      : s === 'cfdi-received'
        ? 'Sólo recibidas'
        : 'Sin CFDI registrados';
}
function sideText(label: string, s: Side) {
  return s.count ? `${label}: ${s.count} · ${money(s.total)}` : `${label}: no hay registradas en ContaSuite`;
}

/** Plan v1.1, Cambio 3: which months and days have issued / received CFDI registered in ContaSuite. */
export default function CfdiCalendar({
  companyId,
  canRebuild,
  notify,
}: {
  companyId: string;
  canRebuild: boolean;
  notify: (s: string) => void;
}) {
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState<number | null>(null);
  const [day, setDay] = useState<number | null>(null);
  const [data, setData] = useState<YearData | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [list, setList] = useState<{ day: string; kind: 'issued' | 'received'; rows: Row[] } | null>(null);
  const [reload, setReload] = useState(0);
  const [rebuilding, setRebuilding] = useState(false);
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setError('');
    api<YearData>(
      `/cfdi-calendar/${companyId}?year=${year}${month ? '&month=' + month : ''}`,
      'GET',
      undefined,
      abort.signal,
    )
      .then(setData)
      .catch((e) => !abort.signal.aborted && setError(e.message))
      .finally(() => !abort.signal.aborted && setLoading(false));
    return () => abort.abort();
  }, [companyId, year, month, reload]);
  async function open(day: number, kind: 'issued' | 'received') {
    const iso = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    try {
      const rows = await api<Row[]>(`/cfdi-calendar/${companyId}/documents?day=${iso}&kind=${kind}`);
      setList({ day: iso, kind, rows });
    } catch (e) {
      notify((e as Error).message);
    }
  }
  async function rebuild() {
    setRebuilding(true);
    try {
      const r = await api<{ indexed: number; skipped: number; pending: boolean }>(
        `/cfdi-calendar/${companyId}/rebuild`,
        'POST',
      );
      notify(
        `Calendario actualizado: ${r.indexed} CFDI indexados` +
          (r.pending ? '; quedan más, vuelve a actualizar.' : '.'),
      );
      setReload((n) => n + 1);
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setRebuilding(false);
    }
  }
  const first = month ? (new Date(year, month - 1, 1).getDay() + 6) % 7 : 0;
  // Rediseño v2: totals of the year (sum of the months the API already returns) and the selected day.
  const yearTotals = (data?.months || []).reduce(
    (t, m) => ({
      issued: { count: t.issued.count + m.issued.count, total: t.issued.total + m.issued.total },
      received: { count: t.received.count + m.received.count, total: t.received.total + m.received.total },
    }),
    { issued: { count: 0, total: 0 }, received: { count: 0, total: 0 } },
  );
  const monthCell = month ? data?.months.find((m) => m.month === month) : undefined;
  const dayCell = day && data?.days ? data.days.find((d) => d.day === day) : undefined;
  const dayLabel = (n: number) =>
    month
      ? new Date(year, month - 1, n).toLocaleDateString('es-MX', { day: 'numeric', month: 'short', year: 'numeric' })
      : '';
  return (
    <section className="v11-calendar v2-calendar" aria-busy={loading}>
      <div className="v2-cal-summary">
        <span className="v2-cal-icon" aria-hidden>
          <CalendarDays size={20} />
        </span>
        <div className="v2-cal-year" role="group" aria-label="Año del calendario">
          <button
            className={stitchButton + ' icon-only'}
            aria-label="Año anterior"
            onClick={() => setYear((y) => y - 1)}
          >
            <ChevronLeft size={16} aria-hidden />
          </button>
          <strong aria-live="polite">Ejercicio {year}</strong>
          <button
            className={stitchButton + ' icon-only'}
            aria-label="Año siguiente"
            onClick={() => setYear((y) => y + 1)}
          >
            <ChevronRight size={16} aria-hidden />
          </button>
        </div>
        <dl className="v2-cal-totals">
          <div>
            <dt>Emitidas (año)</dt>
            <dd className="is-issued">
              {yearTotals.issued.count} · {money(yearTotals.issued.total)}
            </dd>
          </div>
          <div>
            <dt>Recibidas (año)</dt>
            <dd className="is-received">
              {yearTotals.received.count} · {money(yearTotals.received.total)}
            </dd>
          </div>
          <div>
            <dt>Importe total</dt>
            <dd>{money(yearTotals.issued.total + yearTotals.received.total)}</dd>
          </div>
        </dl>
        {canRebuild && (
          <button className={stitchButton} disabled={rebuilding} onClick={rebuild}>
            <RefreshCw size={16} aria-hidden /> {rebuilding ? 'Actualizando…' : 'Actualizar calendario'}
          </button>
        )}
      </div>
      <p className="muted v2-cal-note">
        CFDI registrados en ContaSuite por fecha de emisión. Emitida o recibida según el RFC de la empresa. No hay
        descarga ni consulta al SAT.
      </p>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {loading && !data && <p role="status">Consultando calendario…</p>}
      {data && data.indexed === 0 && (
        <p className="v2-empty muted">
          No hay CFDI indexados para esta empresa.{' '}
          {canRebuild && 'Si ya hay XML en su expediente, usa «Actualizar calendario» para indexarlos.'}
        </p>
      )}
      {data && (
        <>
          <h2 className="v2-cal-heading">
            <CalendarDays size={19} aria-hidden /> Meses del ejercicio {year}
          </h2>
          <div className="v11-months v2-months">
            {data.months.map((m) => (
              <button
                key={m.month}
                className={'v11-month v2-month ' + state(m)}
                aria-pressed={month === m.month}
                aria-label={`${MONTHS[m.month - 1]} ${year}: ${stateText(m)}. ${sideText('Emitidas', m.issued)}. ${sideText('Recibidas', m.received)}.`}
                onClick={() => {
                  setMonth(month === m.month ? null : m.month);
                  setDay(null);
                }}
              >
                <span className="v2-month-name">
                  {MONTHS[m.month - 1]}
                  {month === m.month && <small>Abierto</small>}
                </span>
                <span className={m.issued.count ? 'is-issued' : 'is-missing'}>{sideText('Emitidas', m.issued)}</span>
                <span className={m.received.count ? 'is-received' : 'is-missing'}>
                  {sideText('Recibidas', m.received)}
                </span>
              </button>
            ))}
          </div>
        </>
      )}
      {data?.days && month && (
        <div className="v2-cal-days">
          <div className="v2-cal-days-head">
            <div>
              <h3>
                {MONTHS[month - 1]} {year} · Vista diaria
              </h3>
              <p className="muted">Pulsa un día para consultar sus conteos e importes y abrir el listado de CFDI.</p>
            </div>
            {monthCell && (
              <span className="v2-cal-month-totals">
                {sideText('Emitidas', monthCell.issued)} · {sideText('Recibidas', monthCell.received)}
              </span>
            )}
          </div>
          {dayCell && (
            <div className="v2-cal-selected" role="status">
              <span className="v2-cal-icon" aria-hidden>
                <CalendarDays size={18} />
              </span>
              <div>
                <small>Día seleccionado</small>
                <strong>{dayLabel(dayCell.day)}</strong>
              </div>
              <span className="is-issued">
                <ArrowUp size={15} aria-hidden /> Emitidos (E):{' '}
                {dayCell.issued.count
                  ? `${dayCell.issued.count} · ${money(dayCell.issued.total)}`
                  : 'no hay registrados'}
              </span>
              <span className="is-received">
                <ArrowDown size={15} aria-hidden /> Recibidos (R):{' '}
                {dayCell.received.count
                  ? `${dayCell.received.count} · ${money(dayCell.received.total)}`
                  : 'no hay registrados'}
              </span>
              {(dayCell.issued.count > 0 || dayCell.received.count > 0) && (
                <button
                  className={stitchPrimary}
                  onClick={() => open(dayCell.day, dayCell.issued.count ? 'issued' : 'received')}
                >
                  Ver listado de CFDI <ArrowRight size={16} aria-hidden />
                </button>
              )}
            </div>
          )}
          <div className="v11-days v2-days" role="grid" aria-label={`Días de ${MONTHS[month - 1]} ${year}`}>
            {WEEKDAYS.map((d) => (
              <span key={d} className="v11-weekday" role="columnheader">
                {d}
              </span>
            ))}
            {Array.from({ length: first }, (_, i) => (
              <span key={'e' + i} aria-hidden />
            ))}
            {data.days.map((d) => {
              const label = `${d.day} de ${MONTHS[month - 1].toLowerCase()}: ${stateText(d)}. ${sideText('Emitidas', d.issued)}. ${sideText('Recibidas', d.received)}.`;
              return (
                <button
                  key={d.day}
                  role="gridcell"
                  className={'v11-day v2-day ' + state(d)}
                  title={label}
                  aria-label={label}
                  aria-selected={day === d.day}
                  onClick={() => setDay(d.day)}
                >
                  <strong>{d.day}</strong>
                  <span className="v2-day-counts">
                    {d.issued.count > 0 && (
                      <span className="v2-pill is-issued">
                        <ArrowUp size={11} aria-hidden />
                        {d.issued.count}E
                      </span>
                    )}
                    {d.received.count > 0 && (
                      <span className="v2-pill is-received">
                        <ArrowDown size={11} aria-hidden />
                        {d.received.count}R
                      </span>
                    )}
                    {!d.issued.count && !d.received.count && <MinusCircle size={12} aria-hidden />}
                  </span>
                </button>
              );
            })}
          </div>
          <ul className="v11-calendar-legend v2-cal-legend" aria-label="Simbología">
            <li>
              <span className="v2-swatch cfdi-none" aria-hidden>
                <MinusCircle size={12} />
              </span>
              Sin CFDI
            </li>
            <li>
              <span className="v2-pill is-issued" aria-hidden>
                <ArrowUp size={11} />E
              </span>
              Emitidos (E)
            </li>
            <li>
              <span className="v2-pill is-received" aria-hidden>
                <ArrowDown size={11} />R
              </span>
              Recibidos (R)
            </li>
            <li>
              <span className="v2-swatch cfdi-both" aria-hidden />
              Ambos (E y R)
            </li>
          </ul>
        </div>
      )}
      {list && (
        <Modal
          title={`CFDI ${list.kind === 'issued' ? 'emitidos' : 'recibidos'} del ${new Date(list.day + 'T12:00:00').toLocaleDateString('es-MX')}`}
          onClose={() => setList(null)}
        >
          <div className="actions">
            {(['issued', 'received'] as const).map((k) => (
              <button
                key={k}
                className={stitchButton}
                aria-pressed={list.kind === k}
                onClick={() => open(Number(list.day.slice(8)), k)}
              >
                {k === 'issued' ? 'Emitidas' : 'Recibidas'}
              </button>
            ))}
          </div>
          {list.rows.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Archivo</th>
                    <th scope="col">{list.kind === 'issued' ? 'RFC receptor' : 'RFC emisor'}</th>
                    <th scope="col">Tipo</th>
                    <th scope="col">Total</th>
                    <th scope="col">Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {list.rows.map((r) => (
                    <tr key={r.document_id}>
                      <td title={r.uuid || ''}>{r.name}</td>
                      <td>{r.counterpart_rfc}</td>
                      <td>{r.type}</td>
                      <td>
                        {money(r.total)}
                        {r.currency && r.currency !== 'MXN' ? ' ' + r.currency : ''}
                      </td>
                      <td>
                        <button
                          className={stitchButton}
                          onClick={() => download(r.document_id, r.name).catch((e) => notify(e.message))}
                        >
                          Descargar
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">
              No hay {list.kind === 'issued' ? 'emitidas' : 'recibidas'} registradas en ContaSuite este día.
            </p>
          )}
        </Modal>
      )}
    </section>
  );
}
