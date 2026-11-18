import { useMemo, useState } from 'react';
import type { FinanceRow, Job } from '../types';

const LABELS: Record<string, string> = {
  estados: 'Estados financieros',
  balanza: 'Balanza de comprobación',
  auxiliar: 'Auxiliares',
  diario: 'Libro diario',
  balance: 'Balance general',
  resultados: 'Estado de resultados',
  flujo: 'Flujo de efectivo',
  razones: 'Razones financieras',
  variaciones: 'Variaciones en capital',
  analiticas: 'Analíticas',
  detalle: 'Detalle mensual',
  movimientos: 'Ingresos y gastos',
  anual: 'Archivo anual (.36)',
  mensual: 'Archivo mensual (.38)',
  nomina: 'Visor de nómina',
  otro: 'Otro',
};
const base = (p: string) => p.split('/').pop() || p;

/** Financial statements by scope (subfolder), year and report type. Names only: the numbers are never read. */
export default function FinanceInventory({ job }: { job?: Job }) {
  const data = job?.result.finanzas;
  const [scope, setScope] = useState('');
  const scopes = useMemo(() => [...new Set((data?.rows ?? []).map((r) => r.o))].sort(), [data]);
  if (!job || !data)
    return <p className="muted">Aún no hay inventario. Usa «Analizar carpeta» para que tu agente lo genere.</p>;
  if (!data.total) return <p className="muted">Esta carpeta no tiene estados financieros.</p>;
  const years = new Map<string, Map<string, FinanceRow[]>>();
  for (const r of data.rows.filter((x) => !scope || x.o === scope)) {
    const year = String(r.y ?? 'Sin ejercicio');
    const types = years.get(year) ?? new Map<string, FinanceRow[]>();
    types.set(r.t, [...(types.get(r.t) ?? []), r]);
    years.set(year, types);
  }
  return (
    <div className="finance-inventory">
      <p>
        <strong>Estados financieros</strong> · {data.total} archivos
        {data.dropped > 0 && ' · se muestran los primeros ' + data.rows.length}
      </p>
      <p className="muted">
        Ordenados por subcarpeta, ejercicio y tipo de reporte. No se leen ni se validan las cifras.
      </p>
      {scopes.length > 1 && (
        <div className="toolbar">
          <select aria-label="Subcarpeta" value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="">Todas las subcarpetas</option>
            {scopes.map((s) => (
              <option key={s} value={s}>
                {s || 'Carpeta principal'}
              </option>
            ))}
          </select>
        </div>
      )}
      {[...years.entries()]
        .sort(([a], [b]) => b.localeCompare(a))
        .map(([year, types]) => (
          <details className="imss-month" key={year} open>
            <summary>
              <strong>{year}</strong>
              <span className="chip">{[...types.values()].reduce((n, rows) => n + rows.length, 0)} archivos</span>
            </summary>
            {[...types.entries()].map(([type, rows]) => (
              <div key={type}>
                <p className="muted" style={{ margin: '8px 0 2px' }}>
                  {LABELS[type] || type} · {rows.length}
                </p>
                <ul className="imss-files">
                  {rows.map((r) => (
                    <li key={r.p} title={r.p}>
                      {base(r.p)}
                      {r.n ? <small>mes {r.n}</small> : null}
                      {r.o ? <small>{r.o}</small> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </details>
        ))}
    </div>
  );
}
