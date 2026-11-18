import { useMemo, useState } from 'react';
import { dateLabel } from '../api';
import type { CfdiRow, Job } from '../types';

const MONTHS = [
  'ENERO',
  'FEBRERO',
  'MARZO',
  'ABRIL',
  'MAYO',
  'JUNIO',
  'JULIO',
  'AGOSTO',
  'SEPTIEMBRE',
  'OCTUBRE',
  'NOVIEMBRE',
  'DICIEMBRE',
];
const TIPOS: Record<string, string> = { I: 'Ingreso', E: 'Egreso', P: 'Pago', N: 'Nómina', T: 'Traslado' };
const KINDS: Record<string, string> = { E: 'EMITIDOS', R: 'RECIBIDOS' };
const REASONS: Record<string, string> = {
  mes_distinto: 'El mes de la carpeta no coincide con la fecha del XML.',
  tipo_distinto: 'La carpeta (emitidos/recibidos) no coincide con los RFC del XML.',
  rfc_ajeno: 'Ni el emisor ni el receptor son el RFC de la empresa.',
  rfc_ambiguo: 'El emisor y el receptor son el RFC de la empresa.',
  sin_ubicacion: 'No se pudo determinar el mes o si es emitido/recibido.',
  xml_ilegible: 'No se pudo leer el encabezado del XML.',
};
const PAGE = 50;

const monthLabel = (m: number | null) => (m ? String(m).padStart(2, '0') + '.- ' + MONTHS[m - 1] : 'Sin mes');
const nodeOf = (r: CfdiRow) => (r.s === 'revisar' ? 'revisar' : `${r.y ?? 's/e'}|${r.m ?? 0}|${r.k ?? ''}`);
const base = (p: string) => p.split('/').pop() || p;

/** Virtual CFDI group: CFDI / NN.- MES / EMITIDOS | RECIBIDOS. Reads the last folder analysis; moves nothing. */
export default function CfdiInventory({ job }: { job?: Job }) {
  const cfdi = job?.result.cfdi;
  const [node, setNode] = useState('');
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('');
  const [page, setPage] = useState(0);
  const rows = useMemo(() => cfdi?.rows ?? [], [cfdi]);
  const tree = useMemo(() => {
    const years = new Map<string, Map<number, Map<string, number>>>();
    for (const r of rows) {
      if (r.s === 'revisar') continue;
      const y = String(r.y ?? 's/e');
      const months = years.get(y) ?? new Map();
      const kinds: Map<string, number> = months.get(r.m ?? 0) ?? new Map();
      kinds.set(r.k ?? '', (kinds.get(r.k ?? '') ?? 0) + 1);
      months.set(r.m ?? 0, kinds);
      years.set(y, months);
    }
    return [...years.entries()].sort(([a], [b]) => b.localeCompare(a));
  }, [rows]);
  const shown = useMemo(
    () =>
      rows.filter(
        (r) =>
          (!node || nodeOf(r) === node || (node.endsWith('|*') && nodeOf(r).startsWith(node.slice(0, -1)))) &&
          (!kind || r.g === kind) &&
          (!query || r.p.toLowerCase().includes(query.toLowerCase())),
      ),
    [rows, node, kind, query],
  );
  if (!job || !cfdi)
    return (
      <p className="muted">
        Aún no hay inventario. Usa «Analizar carpeta» para que tu agente clasifique los archivos de la empresa.
      </p>
    );
  const slice = shown.slice(page * PAGE, page * PAGE + PAGE);
  const pick = (value: string) => {
    setNode(value);
    setPage(0);
  };
  return (
    <div className="cfdi-inventory">
      <p>
        <strong>CFDI</strong> · {cfdi.total.toLocaleString('es-MX')} archivos · {cfdi.ok.toLocaleString('es-MX')}{' '}
        ubicados automáticamente · {cfdi.revisar.toLocaleString('es-MX')} por revisar · análisis del{' '}
        {dateLabel(job.created_at)}
      </p>
      <p className="muted">
        Orden virtual CFDI / mes / emitidos o recibidos, tomado del contenido de cada XML y verificado con las carpetas.
        No mueve ni cambia tus archivos.
        {cfdi.dropped > 0 && ' Se muestran los primeros ' + cfdi.rows.length + '.'}
      </p>
      <div className="cfdi-grid">
        <nav aria-label="Estructura virtual CFDI" className="cfdi-tree">
          <button className={node === '' ? 'on' : ''} onClick={() => pick('')}>
            Todos <span>{cfdi.total.toLocaleString('es-MX')}</span>
          </button>
          {cfdi.revisar > 0 && (
            <button className={node === 'revisar' ? 'on warn' : 'warn'} onClick={() => pick('revisar')}>
              Por revisar <span>{cfdi.revisar}</span>
            </button>
          )}
          {tree.map(([year, months]) => (
            <details key={year} open>
              <summary>{year}</summary>
              {[...months.entries()]
                .sort(([a], [b]) => a - b)
                .map(([month, kinds]) => (
                  <div key={month}>
                    <button
                      className={node === `${year}|${month}|*` ? 'on' : ''}
                      onClick={() => pick(`${year}|${month}|*`)}
                    >
                      {monthLabel(month)} <span>{[...kinds.values()].reduce((a, b) => a + b, 0)}</span>
                    </button>
                    {[...kinds.entries()].map(([k, n]) => (
                      <button
                        key={k}
                        className={'sub' + (node === `${year}|${month}|${k}` ? ' on' : '')}
                        onClick={() => pick(`${year}|${month}|${k}`)}
                      >
                        {KINDS[k] || 'Sin tipo'} <span>{n}</span>
                      </button>
                    ))}
                  </div>
                ))}
            </details>
          ))}
        </nav>
        <div>
          <div className="toolbar" style={{ flexWrap: 'wrap' }}>
            <input
              aria-label="Buscar en el inventario CFDI"
              placeholder="Buscar archivo"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
            <select
              aria-label="Tipo de archivo"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                setPage(0);
              }}
            >
              <option value="">XML, PDF y reportes</option>
              <option value="xml">XML</option>
              <option value="pdf">PDF</option>
              <option value="reporte">Reportes SAT</option>
            </select>
          </div>
          <ul className="cfdi-files">
            {slice.map((r) => (
              <li key={r.p} title={r.p}>
                <span className="cfdi-name">
                  {base(r.p)}
                  <small>{r.p}</small>
                </span>
                <span className="chip">{r.g === 'reporte' ? 'Reporte' : r.g.toUpperCase()}</span>
                <span className="chip">{r.t ? TIPOS[r.t] || r.t : '—'}</span>
                <span className={r.s === 'revisar' ? 'chip warn' : 'chip'}>
                  {r.s === 'revisar'
                    ? 'Revisar'
                    : (KINDS[r.k ?? ''] || '—') + ' · ' + (r.m ? monthLabel(r.m).slice(0, 2) + '/' + (r.y ?? '') : '—')}
                </span>
                {r.s === 'revisar' && <small className="cfdi-why">{REASONS[r.why] || r.why}</small>}
              </li>
            ))}
          </ul>
          {!shown.length && <p className="muted">Sin archivos con estos filtros.</p>}
          <div className="pagination">
            <button className="btn" disabled={page === 0} onClick={() => setPage((n) => n - 1)}>
              Anterior
            </button>
            <span>
              {shown.length ? page * PAGE + 1 : 0}–{Math.min(shown.length, page * PAGE + PAGE)} de {shown.length}
            </span>
            <button className="btn" disabled={(page + 1) * PAGE >= shown.length} onClick={() => setPage((n) => n + 1)}>
              Siguiente
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
