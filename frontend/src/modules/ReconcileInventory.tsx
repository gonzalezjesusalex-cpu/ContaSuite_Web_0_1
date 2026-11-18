import { useState } from 'react';
import type { Job } from '../types';

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
const KIND: Record<string, string> = { E: 'Emitidos', R: 'Recibidos' };
const money = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN' });
const base = (p: string) => p.split('/').pop() || p;
const EMPTY = <p className="muted">Aún no hay inventario. Usa «Analizar carpeta» para que tu agente lo genere.</p>;

/** SAT monthly report against the XML in the folder: invoices the SAT lists that have no XML, and the reverse. */
export function ReconcileInventory({ job }: { job?: Job }) {
  const data = job?.result.conciliacion;
  const [onlyIssues, setOnlyIssues] = useState(true);
  if (!job || !data) return EMPTY;
  if (!data.periodos.length) return <p className="muted">No hay reportes del SAT ni XML para conciliar.</p>;
  const periods = data.periodos.filter((p) => !onlyIssues || p.s !== 'ok');
  return (
    <div className="reconcile-inventory">
      <p>
        <strong>Conciliación con el SAT</strong> · {data.con_reporte} meses con reporte · {data.ok} sin diferencias ·{' '}
        {data.faltan_xml} facturas del SAT sin XML · {data.sin_reporte_xml} XML fuera del reporte
      </p>
      <p className="muted">
        Compara los UUID del reporte mensual Emitidos/Recibidos con los XML de la carpeta. No consulta al SAT ni
        acredita nada: el reporte es el archivo que tú descargaste.
      </p>
      <label className="muted">
        <input type="checkbox" checked={onlyIssues} onChange={(e) => setOnlyIssues(e.target.checked)} /> Mostrar sólo
        meses con diferencias
      </label>
      {periods.map((p) => (
        <details className="imss-month" key={`${p.k}${p.y}${p.m}`} open={p.s === 'revisar'}>
          <summary>
            <strong>
              {MONTHS[p.m - 1]} {p.y} · {KIND[p.k]}
            </strong>
            <span className={p.s === 'ok' ? 'chip ok' : 'chip warn'}>
              {p.s === 'ok' ? 'Coincide' : p.s === 'sin_reporte_mes' ? 'Sin reporte del mes' : 'Con diferencias'}
            </span>
          </summary>
          <p className="muted">
            {p.reporte ?? 0} en el reporte · {p.xml} XML en la carpeta · {p.ok} coinciden
          </p>
          {(p.faltan ?? []).length > 0 && (
            <>
              <small className="tax-why revisar">
                {p.n_faltan} factura(s) del SAT sin XML en la carpeta
                {(p.n_faltan ?? 0) > p.faltan.length && ' (primeras ' + p.faltan.length + ')'}:
              </small>
              <ul className="imss-files">
                {p.faltan.map((f) => (
                  <li key={f.u}>
                    <code>{f.u}</code>{' '}
                    <small>
                      {f.fecha} · {f.tipo} · {money(f.total)}
                    </small>
                    {f.cancelado && <small className="tax-why revisar">Cancelado</small>}
                  </li>
                ))}
              </ul>
            </>
          )}
          {(p.sobran ?? []).length > 0 && (
            <>
              <small className="tax-why">
                {p.n_sobran} XML en la carpeta que el reporte del mes no incluye
                {(p.n_sobran ?? 0) > p.sobran.length && ' (primeros ' + p.sobran.length + ')'}:
              </small>
              <ul className="imss-files">
                {p.sobran.map((path) => (
                  <li key={path} title={path}>
                    {base(path)}
                  </li>
                ))}
              </ul>
            </>
          )}
          {p.cancelados > 0 && (
            <small className="tax-why revisar">{p.cancelados} XML de un CFDI marcado como cancelado.</small>
          )}
        </details>
      ))}
      {!periods.length && <p className="muted">Todos los meses coinciden con su reporte.</p>}
    </div>
  );
}

const PPD_STATES: Record<string, string> = {
  parcial: 'Con saldo pendiente',
  sin_pago: 'Sin complemento de pago',
  liquidada: 'Liquidada',
};

/** PPD invoices and the payment complements (CFDI tipo P) that settle them, matched by UUID. */
export function PpdInventory({ job }: { job?: Job }) {
  const data = job?.result.ppd;
  const [state, setState] = useState('');
  if (!job || !data) return EMPTY;
  if (!data.total) return <p className="muted">No hay facturas con método de pago PPD.</p>;
  const rows = data.rows.filter((r) => !state || r.s === state);
  return (
    <div className="ppd-inventory">
      <p>
        <strong>Facturas PPD y sus pagos</strong> · {data.total} facturas · {data.liquidadas} liquidadas ·{' '}
        {data.parcial} con saldo · {data.sin_pago} sin pago
      </p>
      <p className="muted">
        Cruza cada factura PPD con los complementos de pago de esta carpeta por UUID. Un pago puede estar en otra
        carpeta o en un periodo posterior: «sin pago» significa sin complemento aquí, no que no se haya pagado.
      </p>
      {data.pagos_ajenos > 0 && (
        <p className="tax-why">
          {data.pagos_ajenos} complemento(s) de pago apuntan a facturas PPD que no están en esta carpeta.
        </p>
      )}
      <div className="toolbar">
        <select aria-label="Estado del pago" value={state} onChange={(e) => setState(e.target.value)}>
          <option value="">Todos los estados</option>
          {Object.entries(PPD_STATES).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </div>
      <ul className="cfdi-files">
        {rows.map((r) => (
          <li key={r.u} title={r.p}>
            <span className="cfdi-name">
              {base(r.p)}
              <small>
                {KIND[r.k ?? ''] || '—'} · {r.m ? MONTHS[r.m - 1] : '—'} {r.y ?? ''} · total {money(r.tot)}
              </small>
            </span>
            <span className="chip">{r.pagos} pago(s)</span>
            <span className="chip">pagado {money(r.pagado)}</span>
            <span className={r.s === 'liquidada' ? 'chip ok' : 'chip warn'}>
              {PPD_STATES[r.s]}
              {r.s === 'parcial' && ' · saldo ' + money(r.saldo)}
            </span>
          </li>
        ))}
      </ul>
      {data.total > data.rows.length && <p className="muted">Se muestran las primeras {data.rows.length}.</p>}
    </div>
  );
}
