import { ShieldCheck } from 'lucide-react';
import { dateLabel } from '../api';
import { stitchButton } from '../components/stitch';
import { CERT_KIND_LABEL, CERT_STATE_LABEL, certState } from '../certStatus';
import type { Job } from '../types';

/** «Detectados en la carpeta» (cambio 2.4): unique public certificates found by the last folder analysis.
 * No names or paths are shown; registering is always an action of the user through the existing flow. */
export default function DetectedCertificates({
  job,
  canRegister,
  onRegister,
}: {
  job?: Job;
  canRegister: boolean;
  onRegister: (kind: 'fiel' | 'csd' | 'unknown') => void;
}) {
  const data = job?.result.certificados;
  return (
    <section className="detected-certs" aria-labelledby="detected-certs-title">
      <h3 id="detected-certs-title">
        <ShieldCheck size={17} aria-hidden="true" /> Detectados en la carpeta
      </h3>
      {!data ? (
        <p className="muted">Aún no hay análisis de la carpeta. Usa «Analizar carpeta» para detectar certificados.</p>
      ) : !data.rows.length ? (
        <p className="muted">No se encontraron certificados (.cer) en la carpeta.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Tipo</th>
                <th>RFC</th>
                <th>Serie</th>
                <th>Vence</th>
                <th>Días</th>
                <th>Estado</th>
                <th>Titular</th>
                <th>Acción</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r, i) => {
                const { state, days } = certState(r);
                const readable = state !== 'ilegible';
                return (
                  <tr key={(r.serie || r.p) + i}>
                    <td>{CERT_KIND_LABEL[r.k]}</td>
                    <td>{r.rfcs.length ? r.rfcs.join(', ') : '—'}</td>
                    <td title="Número de serie">{r.serie ? '…' + r.serie.slice(-6) : '—'}</td>
                    <td>{r.hasta ? dateLabel(r.hasta) : '—'}</td>
                    <td>{readable && days !== null ? days : '—'}</td>
                    <td>
                      <span
                        className={
                          state === 'vigente' ? 'chip ok' : state === 'por_vencer' ? 'chip warn' : 'chip danger'
                        }
                      >
                        {CERT_STATE_LABEL[state]}
                      </span>
                    </td>
                    <td>{!r.rfcs.length ? '—' : r.emp ? 'De la empresa' : 'RFC distinto'}</td>
                    <td>
                      <button
                        type="button"
                        className={stitchButton}
                        disabled={!canRegister || !readable}
                        onClick={() => onRegister(r.k === 'FIEL' ? 'fiel' : r.k === 'CSD' ? 'csd' : 'unknown')}
                      >
                        Registrar
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted">
        Vigencia según el archivo .cer; no confirma revocación ni validación SAT. «RFC distinto» es sólo informativo: un
        certificado nunca se asocia solo a la empresa.
      </p>
    </section>
  );
}
