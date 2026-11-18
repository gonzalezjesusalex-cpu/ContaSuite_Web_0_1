import { useEffect, useState } from 'react';
import { api, dateLabel } from '../api';
import type { Job, VirtualFileRow, VirtualIndexSummary } from '../types';

type Filter = { key: string; label: string; query: string; count: (d: VirtualIndexSummary) => number };

const FILTERS: Filter[] = [
  { key: 'added', label: 'Nuevos', query: 'change=added', count: (d) => d.latest?.added ?? 0 },
  { key: 'changed', label: 'Cambiaron de contenido', query: 'change=changed', count: (d) => d.latest?.changed ?? 0 },
  { key: 'moved', label: 'Cambiaron de lugar', query: 'change=moved', count: (d) => d.latest?.moved ?? 0 },
  { key: 'restored', label: 'Volvieron a aparecer', query: 'change=restored', count: (d) => d.latest?.restored ?? 0 },
  { key: 'missing', label: 'Ya no están', query: 'missing=true', count: (d) => d.missing },
  { key: 'with_copy', label: 'Con copia interna', query: 'copied=true', count: (d) => d.copia.con_copia },
  { key: 'without_copy', label: 'Sin copia interna', query: 'copied=false', count: (d) => d.copia.pendientes },
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

/** What changed since the previous analysis, and which files have an internal copy, from the server's virtual index. */
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
    const selected = FILTERS.find((f) => f.key === filter);
    if (!selected) {
      setRows([]);
      return;
    }
    const abort = new AbortController();
    setLoading(true);
    api<{ rows: VirtualFileRow[]; total: number; more: boolean }>(
      `/companies/${companyId}/virtual-index/files?${selected.query}&offset=${offset}&limit=${PAGE}`,
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
  return (
    <div className="changes-inventory">
      <p>
        <strong>Índice guardado</strong> · {data.total.toLocaleString('es-MX')} archivos
        {data.missing > 0 && ` · ${data.missing} ya no están`}
        {latest && ` · último análisis ${dateLabel(latest.created_at)}`}
      </p>
      <p>
        <strong>Copia interna</strong> · {data.copia.con_copia.toLocaleString('es-MX')} archivos con copia (
        {size(data.copia.bytes)})
        {data.copia.pendientes > 0 && ` · ${data.copia.pendientes.toLocaleString('es-MX')} sin copia`}
      </p>
      <p className="muted">
        Se guarda la ruta, el tamaño y la huella de cada archivo, para saber qué cambió entre análisis. La copia interna
        del contenido sólo existe donde la pidas con «Guardar copia interna» en el menú ⋯ de la empresa; sirve para
        abrir un archivo aunque su original ya no esté. La e.firma, las llaves y las contraseñas nunca se guardan. Los
        originales no se tocan.
      </p>
      {latest && !latest.complete && (
        <p className="tax-why">El último recorrido llegó a su límite: esa vez no se comparó qué archivos faltan.</p>
      )}
      <div className="inventory-sections" role="group" aria-label="Qué mostrar">
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
            {f.label} {f.count(data)}
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
                {r.copied && (
                  <a
                    className="chip ok"
                    href={`/api/companies/${companyId}/virtual-index/files/${r.id}/content`}
                    aria-label={`Descargar la copia interna de ${r.name}`}
                  >
                    Copia interna · descargar
                  </a>
                )}
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
