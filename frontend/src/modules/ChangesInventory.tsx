import { useEffect, useState } from 'react';
import { api, dateLabel } from '../api';
import type { Job, VirtualFileRow, VirtualIndexSummary } from '../types';

const FILTERS: { key: string; label: string; field: 'added' | 'changed' | 'moved' | 'restored' | 'missing' }[] = [
  { key: 'added', label: 'Nuevos', field: 'added' },
  { key: 'changed', label: 'Cambiaron de contenido', field: 'changed' },
  { key: 'moved', label: 'Cambiaron de lugar', field: 'moved' },
  { key: 'restored', label: 'Volvieron a aparecer', field: 'restored' },
  { key: 'missing', label: 'Ya no están', field: 'missing' },
];
const SECTIONS: Record<string, string> = {
  cfdi: 'CFDI',
  impuestos: 'Impuestos',
  imss: 'IMSS',
  nomina: 'Nómina',
  expediente: 'Expediente',
  finanzas: 'Estados financieros',
  trabajadores: 'Trabajadores',
  sin_clasificar: 'Sin clasificar',
};
const PAGE = 50;
const size = (b: number) =>
  b >= 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';

/** What changed since the previous analysis, from the persistent virtual index kept by the server. */
export default function ChangesInventory({ companyId, job }: { job?: Job; companyId: string }) {
  const [data, setData] = useState<VirtualIndexSummary | null>(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');
  const [rows, setRows] = useState<VirtualFileRow[]>([]);
  const [more, setMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const jobId = job?.id;

  useEffect(() => {
    const abort = new AbortController();
    setError('');
    api<VirtualIndexSummary>(`/companies/${companyId}/virtual-index/summary`, 'GET', undefined, abort.signal)
      .then(setData)
      .catch((e) => !abort.signal.aborted && setError((e as Error).message));
    return () => abort.abort();
  }, [companyId, jobId]);

  useEffect(() => {
    if (!filter) {
      setRows([]);
      return;
    }
    const abort = new AbortController();
    setLoading(true);
    const query = filter === 'missing' ? 'missing=true' : 'change=' + filter;
    api<{ rows: VirtualFileRow[]; total: number; more: boolean }>(
      `/companies/${companyId}/virtual-index/files?${query}&offset=${offset}&limit=${PAGE}`,
      'GET',
      undefined,
      abort.signal,
    )
      .then((r) => {
        setRows(r.rows);
        setMore(r.more);
        setTotal(r.total);
      })
      .catch((e) => !abort.signal.aborted && setError((e as Error).message))
      .finally(() => !abort.signal.aborted && setLoading(false));
    return () => abort.abort();
  }, [companyId, filter, offset, jobId]);

  if (error)
    return (
      <p role="alert" className="error-banner">
        {error}
      </p>
    );
  if (!data) return <p role="status">Consultando el índice guardado…</p>;
  if (!data.scans.length)
    return <p className="muted">Aún no hay índice guardado. Usa «Analizar carpeta» y quedará registrado aquí.</p>;
  const latest = data.latest;
  const counts = (field: (typeof FILTERS)[number]['field']) =>
    field === 'missing' ? data.missing : (latest?.[field] ?? 0);
  return (
    <div className="changes-inventory">
      <p>
        <strong>Índice guardado</strong> · {data.total.toLocaleString('es-MX')} archivos
        {data.missing > 0 && ` · ${data.missing} ya no están`}
        {latest && ` · último análisis ${dateLabel(latest.created_at)}`}
      </p>
      <p className="muted">
        Se guarda la ruta, el tamaño y la huella de cada archivo (no su contenido), para saber qué cambió entre
        análisis. La e.firma, las llaves y las contraseñas nunca se guardan. Los archivos originales no se tocan.
      </p>
      {latest && !latest.complete && (
        <p className="tax-why">El último recorrido llegó a su límite: esa vez no se comparó qué archivos faltan.</p>
      )}
      <div className="inventory-sections" role="group" aria-label="Qué cambió">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            className={'chip' + (filter === f.key ? ' on' : '')}
            aria-pressed={filter === f.key}
            onClick={() => {
              setOffset(0);
              setFilter(filter === f.key ? '' : f.key);
            }}
          >
            {f.label} {counts(f.field)}
          </button>
        ))}
      </div>
      {filter && (
        <>
          {loading && <p role="status">Consultando…</p>}
          {!loading && !rows.length && <p className="muted">Nada en esta categoría.</p>}
          <ul className="cfdi-files">
            {rows.map((r) => (
              <li key={r.id} title={r.path}>
                <span className="cfdi-name">
                  {r.name}
                  <small>{r.path}</small>
                  {r.moved_from && <small>Antes estaba en: {r.moved_from}</small>}
                  {r.missing_since && <small>Ya no está desde el {dateLabel(r.missing_since)}</small>}
                </span>
                <span className="chip">{SECTIONS[r.section] ?? r.section}</span>
                <span className="chip">{size(r.size)}</span>
                {r.state === 'revisar' && <span className="chip warn">Por revisar</span>}
              </li>
            ))}
          </ul>
          <div className="pagination">
            <button className="btn" disabled={offset === 0} onClick={() => setOffset((n) => Math.max(0, n - PAGE))}>
              Anterior
            </button>
            <span>
              {total ? offset + 1 : 0}–{Math.min(total, offset + PAGE)} de {total}
            </span>
            <button className="btn" disabled={!more} onClick={() => setOffset((n) => n + PAGE)}>
              Siguiente
            </button>
          </div>
        </>
      )}
      <h4 className="section-subtitle">Análisis recientes</h4>
      <ul className="imss-files">
        {data.scans.map((s) => (
          <li key={s.id}>
            {dateLabel(s.created_at)} · {s.total} archivos
            <small>
              {s.finished_at
                ? `+${s.added} nuevos · ${s.changed} cambiaron · ${s.moved} movidos · ${s.restored} volvieron · ${s.missing} ya no están`
                : 'no terminó de guardarse'}
              {s.finished_at && !s.complete && ' · recorrido incompleto'}
            </small>
          </li>
        ))}
      </ul>
    </div>
  );
}
