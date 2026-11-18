import { useState } from 'react';
import { dateLabel } from '../api';
import type { ImssRow, Job } from '../types';

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
const COMPONENTS: Record<string, string> = {
  sua: 'SUA',
  sipare: 'SIPARE',
  resumen: 'Resumen de liquidación',
  cedula: 'Cédula',
  cedula_bim: 'Cédula bimestral',
  confronta: 'Confronta',
  diferencias: 'Reporte de diferencias',
  log: 'Log de error del SUA',
  ema: 'EMA',
  eba: 'EBA',
  excel: 'Excel IDSE',
  idse_txt: 'Archivos IDSE',
  otro: 'Otro',
};
const CORE = ['sua', 'sipare', 'resumen', 'cedula', 'cedula_bim', 'confronta'];
const STATES: Record<string, string> = {
  completo: 'Completo',
  faltante: 'Con faltantes',
  parcial: 'Sólo emisiones',
  revisar: 'Por revisar',
};
const NOTES: Record<string, string> = {
  varios_folios: 'Hay más de un folio del SUA en este mes.',
  log_error: 'El SUA dejó un log de error: no pudo generar la línea de captura.',
};
const WHY: Record<string, string> = {
  mes_distinto: 'El mes del nombre del archivo no coincide con su carpeta.',
  sin_mes: 'No se pudo determinar el mes.',
};
const base = (p: string) => p.split('/').pop() || p;

/** Monthly IMSS package (SUA, SIPARE, liquidación, cédulas, confronta, IDSE emissions) and what is missing. */
export default function ImssInventory({ job }: { job?: Job }) {
  const imss = job?.result.imss;
  const [state, setState] = useState('');
  if (!job || !imss)
    return <p className="muted">Aún no hay inventario. Usa «Analizar carpeta» para que tu agente lo genere.</p>;
  const rowsOf = (y: number | null, m: number) => imss.rows.filter((r) => r.y === y && r.m === m);
  const months = imss.months.filter((m) => !state || m.s === state);
  const loose = imss.rows.filter((r) => !r.m && r.s === 'revisar');
  return (
    <div className="imss-inventory">
      <p>
        <strong>IMSS</strong> · {imss.total} archivos · {imss.completos} meses completos · {imss.faltantes} con
        faltantes · {imss.revisar} por revisar · análisis del {dateLabel(job.created_at)}
      </p>
      <p className="muted">
        Paquete mensual armado con el nombre y la carpeta de cada archivo. No acredita el pago ni abre los documentos.
      </p>
      {imss.registros > 1 && (
        <p className="tax-why">
          Hay documentos de {imss.registros} registros patronales distintos: revisa que ninguno sea de otra empresa.
        </p>
      )}
      <div className="toolbar">
        <select aria-label="Estado del mes" value={state} onChange={(e) => setState(e.target.value)}>
          <option value="">Todos los meses</option>
          {Object.entries(STATES).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </div>
      {months.map((m) => {
        const wanted = CORE.filter((c) => m.have.includes(c) || m.faltan.includes(c));
        return (
          <details className="imss-month" key={`${m.y}-${m.m}`}>
            <summary>
              <strong>
                {MONTHS[m.m - 1]} {m.y}
              </strong>
              <span className={m.s === 'completo' || m.s === 'parcial' ? 'chip' : 'chip warn'}>{STATES[m.s]}</span>
            </summary>
            <div className="imss-chips">
              {wanted.map((c) => (
                <span key={c} className={m.faltan.includes(c) ? 'chip warn' : 'chip ok'}>
                  {m.faltan.includes(c) ? 'Falta ' : ''}
                  {COMPONENTS[c]}
                </span>
              ))}
            </div>
            {m.sin_emision.length > 0 && (
              <p className="muted">Sin emisión del IDSE: {m.sin_emision.map((c) => COMPONENTS[c]).join(', ')}.</p>
            )}
            {m.notas.map((n) => (
              <small className="tax-why" key={n}>
                {NOTES[n] || n}
              </small>
            ))}
            <ul className="imss-files">
              {rowsOf(m.y, m.m).map((r: ImssRow) => (
                <li key={r.p} title={r.p}>
                  {base(r.p)}{' '}
                  <small>
                    {COMPONENTS[r.c]}
                    {r.fo ? ' · copia en ' + r.fo : ''}
                  </small>
                  {r.why && <small className="tax-why revisar">{WHY[r.why] || r.why}</small>}
                </li>
              ))}
            </ul>
          </details>
        );
      })}
      {loose.length > 0 && (
        <section className="tax-block">
          <h4>Sin mes determinado</h4>
          {loose.map((r) => (
            <div className="tax-entry" key={r.p} title={r.p}>
              {base(r.p)} <small className="tax-why revisar">{WHY[r.why] || r.why}</small>
            </div>
          ))}
        </section>
      )}
      {imss.generales > 0 && (
        <p className="muted">
          {imss.generales} archivos IMSS generales (Afil/Aseg/Movt, lotes IDSE de trabajadores y avisos) no pertenecen a
          un mes.
        </p>
      )}
      {!months.length && <p className="muted">Sin meses con este estado.</p>}
    </div>
  );
}
