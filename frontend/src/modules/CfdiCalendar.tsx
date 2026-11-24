import { useEffect, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { api, download } from '../api';
import { Modal } from '../components/ui';
import { stitchButton, stitchCard } from '../components/stitch';
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
const MONTHS = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
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
      const r = await api<{ indexed: number; skipped: number; pending: boolean }>(`/cfdi-calendar/${companyId}/rebuild`, 'POST');
      notify(`Calendario actualizado: ${r.indexed} CFDI indexados` + (r.pending ? '; quedan más, vuelve a actualizar.' : '.'));
      setReload((n) => n + 1);
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setRebuilding(false);
    }
  }
  const first = month ? (new Date(year, month - 1, 1).getDay() + 6) % 7 : 0;
  return (
    <section className={stitchCard + ' padded v11-calendar'} aria-busy={loading}>
      <div className="card-title">
        <div>
          <h2>
            <CalendarDays size={19} aria-hidden /> Calendario de CFDI
          </h2>
          <p>
            CFDI registrados en ContaSuite por fecha de emisión. Emitida o recibida según el RFC de la empresa. No hay
            descarga ni consulta al SAT.
          </p>
        </div>
        <div className="actions">
          <button className={stitchButton} aria-label="Año anterior" onClick={() => setYear((y) => y - 1)}>
            <ChevronLeft size={16} aria-hidden />
          </button>
          <strong aria-live="polite">{year}</strong>
          <button className={stitchButton} aria-label="Año siguiente" onClick={() => setYear((y) => y + 1)}>
            <ChevronRight size={16} aria-hidden />
          </button>
          {canRebuild && (
            <button className={stitchButton} disabled={rebuilding} onClick={rebuild}>
              <RefreshCw size={16} aria-hidden /> {rebuilding ? 'Actualizando…' : 'Actualizar calendario'}
            </button>
          )}
        </div>
      </div>
      <ul className="v11-calendar-legend" aria-label="Simbología">
        {(
          [
            ['cfdi-both', 'Emitidas y recibidas'],
            ['cfdi-issued', 'Sólo emitidas'],
            ['cfdi-received', 'Sólo recibidas'],
            ['cfdi-none', 'Sin CFDI registrados'],
          ] as const
        ).map(([k, l]) => (
          <li key={k} className={k}>
            <span className="v11-swatch" aria-hidden />
            <span style={{ color: 'var(--text)' }}>{l}</span>
          </li>
        ))}
      </ul>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {data && data.indexed === 0 && (
        <p className="muted">
          No hay CFDI indexados para esta empresa.{' '}
          {canRebuild && 'Si ya hay XML en su expediente, usa «Actualizar calendario» para indexarlos.'}
        </p>
      )}
      {data && (
        <div className="v11-months">
          {data.months.map((m) => (
            <button
              key={m.month}
              className={'v11-month ' + state(m)}
              aria-pressed={month === m.month}
              aria-label={`${MONTHS[m.month - 1]} ${year}: ${stateText(m)}. ${sideText('Emitidas', m.issued)}. ${sideText('Recibidas', m.received)}.`}
              onClick={() => setMonth(month === m.month ? null : m.month)}
            >
              <h4>
                <span className="v11-swatch" aria-hidden />
                <span style={{ color: 'var(--text)' }}>{MONTHS[m.month - 1]}</span>
              </h4>
              <p className={m.issued.count ? '' : 'is-missing'}>{sideText('Emitidas', m.issued)}</p>
              <p className={m.received.count ? '' : 'is-missing'}>{sideText('Recibidas', m.received)}</p>
            </button>
          ))}
        </div>
      )}
      {data?.days && month && (
        <>
          <h3>
            {MONTHS[month - 1]} {year}
          </h3>
          <div className="v11-days" role="grid" aria-label={`Días de ${MONTHS[month - 1]} ${year}`}>
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
              const kind = d.issued.count ? 'issued' : d.received.count ? 'received' : null;
              return (
                <button
                  key={d.day}
                  role="gridcell"
                  className={'v11-day ' + state(d)}
                  title={label}
                  aria-label={label}
                  disabled={!kind}
                  onClick={() => kind && open(d.day, kind)}
                >
                  <strong style={{ color: 'var(--text)' }}>{d.day}</strong>
                  {d.issued.count > 0 && <span>E {d.issued.count}</span>}
                  {d.received.count > 0 && <span>R {d.received.count}</span>}
                </button>
              );
            })}
          </div>
        </>
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
                        <button className={stitchButton} onClick={() => download(r.document_id, r.name).catch((e) => notify(e.message))}>
                          Descargar
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">No hay {list.kind === 'issued' ? 'emitidas' : 'recibidas'} registradas en ContaSuite este día.</p>
          )}
        </Modal>
      )}
    </section>
  );
}
