import { dateLabel } from '../api';
import type { Job } from '../types';

const KIND: Record<string, string> = {
  FIEL: 'e.firma (FIEL)',
  CSD: 'Sello digital (CSD)',
  RL: 'Representante legal',
  '': 'Certificado',
};
const STATE: Record<string, string> = {
  vigente: 'Vigente',
  por_vencer: 'Por vencer',
  vencido: 'Vencido',
  aun_no: 'Aún no vigente',
  ilegible: 'No se pudo leer',
};
const base = (p: string) => p.split('/').pop() || p;

/** Validity window of the PUBLIC certificates (.cer). Private keys and passwords are never opened. */
export default function CertInventory({ job }: { job?: Job }) {
  const data = job?.result.certificados;
  if (!job || !data)
    return <p className="muted">Aún no hay inventario. Usa «Analizar carpeta» para que tu agente lo genere.</p>;
  if (!data.total) return <p className="muted">No se encontraron certificados (.cer) en la carpeta.</p>;
  return (
    <div className="cert-inventory">
      <p>
        <strong>e.firma y sello digital</strong> · {data.total} certificados · {data.vigentes} vigentes ·{' '}
        {data.por_vencer} por vencer · {data.vencidos} vencidos
      </p>
      <p className="tax-why">
        Sólo se lee el certificado público (.cer). Las llaves privadas y las contraseñas no se abren. Las fechas son las
        del propio certificado: no son una validación del SAT ni revisan revocación.
      </p>
      {data.rows.map((r) => (
        <div className="tax-entry" key={r.p} title={r.p}>
          <div className="tax-docs">
            <span>
              <small>{KIND[r.k]}</small>
              {base(r.p)}
            </span>
            <span>
              <small>Vigencia</small>
              {r.desde ? `${dateLabel(r.desde)} a ${dateLabel(r.hasta)}` : '—'}
              {r.dias !== null && r.s !== 'vencido' && r.s !== 'ilegible' && <small> · {r.dias} días restantes</small>}
            </span>
            <span>
              <small>RFC del titular</small>
              {r.rfcs.length ? r.rfcs.join(', ') : '—'}
              {r.rfcs.length > 0 && !r.emp && <small> · incluye un RFC distinto al de la empresa</small>}
            </span>
          </div>
          <span className={r.s === 'vigente' ? 'chip ok' : 'chip warn'}>{STATE[r.s]}</span>
          {r.why === 'rfc_ajeno' && (
            <small className="tax-why revisar">Un sello digital debe traer el RFC de la empresa.</small>
          )}
        </div>
      ))}
    </div>
  );
}
