import type { Job } from '../types';

const WORKER_LABELS: Record<string, string> = {
  alta: 'Alta IMSS',
  nss: 'Número de seguridad social',
  ine: 'INE',
  csf: 'CSF / CIF',
  curp: 'CURP',
  domicilio: 'Comprobante de domicilio',
  idse: 'Lote IDSE / recibo del IMSS',
  combinado: 'Documentos reunidos',
  otro: 'Otro',
};
const WORKER_REQUIRED = ['alta', 'nss', 'ine', 'csf'];
const base = (p: string) => p.split('/').pop() || p;

/** Payroll by quincena: each CFDI de nómina (XML) with its recibo PDF, plus what is unpaired. */
export function PayrollInventory({ job }: { job?: Job }) {
  const data = job?.result.nomina;
  if (!job || !data)
    return <p className="muted">Aún no hay inventario. Usa «Analizar carpeta» para que tu agente lo genere.</p>;
  if (!data.quincenas.length) return <p className="muted">No se encontraron recibos de nómina por quincena.</p>;
  return (
    <div className="payroll-inventory">
      <p>
        <strong>Nómina</strong> · {data.quincenas.length} quincenas · {data.completas} completas · {data.faltantes} con
        recibos sin par
      </p>
      <p className="muted">
        Cada XML de nómina se empareja con su recibo PDF si tienen el mismo nombre en la misma carpeta.
      </p>
      {data.huecos.length > 0 && (
        <p className="tax-why">
          Sin documentos de las quincenas: {data.huecos.join(', ')}. Entre la primera y la última hay un salto.
        </p>
      )}
      {data.quincenas.map((q) => (
        <details className="imss-month" key={`${q.y}-${q.q}`}>
          <summary>
            <strong>
              {q.label} {q.y}
            </strong>
            <span className={q.s === 'completo' ? 'chip' : 'chip warn'}>
              {q.xml} XML · {q.pdf} PDF
            </span>
          </summary>
          {(q.sin_pdf > 0 || q.sin_xml > 0) && (
            <small className="tax-why">
              {q.sin_pdf > 0 && `${q.sin_pdf} XML sin recibo PDF. `}
              {q.sin_xml > 0 && `${q.sin_xml} recibo(s) PDF sin XML.`}
            </small>
          )}
          <ul className="imss-files">
            {q.files.map((p) => (
              <li key={p} title={p}>
                {base(p)}
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  );
}

/** One folder per worker with the essential documents each one has. Personal data: handle with care. */
export function WorkersInventory({ job }: { job?: Job }) {
  const data = job?.result.trabajadores;
  if (!job || !data)
    return <p className="muted">Aún no hay inventario. Usa «Analizar carpeta» para que tu agente lo genere.</p>;
  if (!data.total) return <p className="muted">No se encontraron expedientes de trabajadores.</p>;
  return (
    <div className="workers-inventory">
      <p>
        <strong>Trabajadores</strong> · {data.personas} personas · {data.incompletos} con documentos faltantes
      </p>
      <p className="tax-why">
        Contiene datos personales (identificaciones, seguridad social). Sólo se listan nombres de archivo; no se abren.
      </p>
      {data.workers.map((w) => (
        <details className="imss-month" key={w.w || 'sin-carpeta'}>
          <summary>
            <strong>{w.w || 'Sin carpeta individual'}</strong>
            <span className={w.faltan.length ? 'chip warn' : 'chip'}>{w.count} archivos</span>
          </summary>
          {w.w && (
            <div className="imss-chips">
              {WORKER_REQUIRED.map((k) => (
                <span key={k} className={w.faltan.includes(k) ? 'chip warn' : 'chip ok'}>
                  {w.faltan.includes(k) ? 'Falta ' : ''}
                  {WORKER_LABELS[k]}
                </span>
              ))}
            </div>
          )}
          <ul className="imss-files">
            {w.files.map((f) => (
              <li key={f.p} title={f.p}>
                {base(f.p)} <small>{WORKER_LABELS[f.t] || f.t}</small>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  );
}
