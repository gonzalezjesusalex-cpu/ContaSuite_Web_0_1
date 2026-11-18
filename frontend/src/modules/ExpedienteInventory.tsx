import type { Job } from '../types';

const LABELS: Record<string, string> = {
  acta: 'Acta constitutiva o de asamblea',
  rpc: 'Registro público de comercio (RPC)',
  csf: 'Constancia de situación fiscal',
  patronal: 'Registro o tarjeta patronal',
  ine: 'Identificación (INE / CURP)',
  repse: 'REPSE',
  objeto: 'Objeto social',
  domicilio: 'Comprobante de domicilio',
  nomina_muestra: 'Recibo de nómina de muestra',
  otro: 'Otro documento',
};
const REQUIRED = ['acta', 'rpc', 'csf', 'patronal', 'ine'];
const base = (p: string) => p.split('/').pop() || p;

/** Company file: constitutive documents, CSF, REPSE, registro patronal and the representative's ID. */
export default function ExpedienteInventory({ job }: { job?: Job }) {
  const data = job?.result.expediente;
  if (!job || !data)
    return <p className="muted">Aún no hay inventario. Usa «Analizar carpeta» para que tu agente lo genere.</p>;
  const groups = Object.entries(
    data.rows.reduce<Record<string, typeof data.rows>>((acc, r) => {
      (acc[r.t] ||= []).push(r);
      return acc;
    }, {}),
  ).sort(([a], [b]) => Object.keys(LABELS).indexOf(a) - Object.keys(LABELS).indexOf(b));
  return (
    <div className="expediente-inventory">
      <p>
        <strong>Expediente de la empresa</strong> · {data.total} documentos ·{' '}
        {data.faltan.length ? data.faltan.length + ' esenciales faltan' : 'esenciales completos'}
      </p>
      <p className="muted">
        Se reconoce por el nombre y la carpeta de cada archivo; no se valida su contenido ni su vigencia.
      </p>
      <div className="imss-chips">
        {REQUIRED.map((k) => (
          <span key={k} className={data.faltan.includes(k) ? 'chip warn' : 'chip ok'}>
            {data.faltan.includes(k) ? 'Falta ' : ''}
            {LABELS[k]}
          </span>
        ))}
      </div>
      {groups.map(([kind, rows]) => (
        <section className="tax-block" key={kind}>
          <h4>
            {LABELS[kind] || kind} <small>{rows.length}</small>
          </h4>
          {rows.map((r) => (
            <div className="tax-entry" key={r.p} title={r.p}>
              {base(r.p)}
              {r.o && <small className="muted"> · {r.o}</small>}
              {r.s === 'revisar' && (
                <small className="tax-why revisar">El RFC del nombre del archivo no es el de esta empresa.</small>
              )}
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
