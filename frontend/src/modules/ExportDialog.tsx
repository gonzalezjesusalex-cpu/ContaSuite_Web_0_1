import { useMemo, useState } from 'react';
import { api } from '../api';
import { Field, Modal } from '../components/ui';
import type { Company, Job } from '../types';

const SECTIONS: Record<string, string> = {
  cfdi: 'CFDI',
  impuestos: 'Impuestos',
  imss: 'IMSS',
  nomina: 'Nómina',
  expediente: 'Expediente de la empresa',
  finanzas: 'Estados financieros',
  sin_clasificar: 'Sin clasificar (conserva sus carpetas originales)',
  trabajadores: 'Trabajadores (datos personales)',
};
const EXCLUDED: Record<string, string> = {
  credenciales: 'e.firma y sello digital',
  contrasenas: 'notas de contraseñas',
  ruido: 'archivos de sistema',
};
const DEFAULT_ON = Object.keys(SECTIONS).filter((k) => k !== 'trabajadores');
const size = (b: number) => (b >= 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB');
const same = (a: string, b: string) => a.trim().replace(/\//g, '\\').toLowerCase() === b.trim().replace(/\//g, '\\').toLowerCase();

/** Export a COPY of the company's folder in the virtual order: preview first, then copy. Originals are never touched. */
export default function ExportDialog({
  company,
  jobs,
  agentReady,
  blockedReason,
  refresh,
  notify,
  onClose,
}: {
  company: Company;
  jobs: Job[];
  agentReady: boolean;
  blockedReason: string | null;
  refresh: () => Promise<void>;
  notify: (m: string) => void;
  onClose: () => void;
}) {
  const parent = company.folder ? company.folder.replace(/[\\/][^\\/]+[\\/]?$/, '') : '';
  const [destination, setDestination] = useState(
    parent ? `${parent}\\Exportaciones ContaSuite\\${company.name.replace(/[<>:"/\\|?*]/g, ' ').trim()}` : '',
  );
  const [include, setInclude] = useState<string[]>(DEFAULT_ON);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const job = jobs.find((j) => j.kind === 'export_virtual');
  const active = !!job && (job.status === 'queued' || job.status === 'running');
  const result = job?.result;
  const matches = useMemo(
    () =>
      !!result?.destination &&
      same(result.destination, destination) &&
      !!result.include &&
      result.include.length === include.length &&
      include.every((k) => result.include!.includes(k)),
    [result, destination, include],
  );
  const toggle = (key: string) => setInclude((list) => (list.includes(key) ? list.filter((k) => k !== key) : [...list, key]));
  async function send(apply: boolean) {
    setBusy(true);
    setError('');
    try {
      await api('/jobs', 'POST', { company_id: company.id, kind: 'export_virtual', destination: destination.trim(), apply, include });
      await refresh();
      notify(apply ? 'Copia enviada a tu agente.' : 'Vista previa enviada a tu agente.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const preview = job?.status === 'completed' && result?.mode === 'preview' && matches ? result : null;
  const done = job?.status === 'completed' && result?.mode === 'apply' && !busy ? result : null;
  return (
    <Modal title="Exportar copia ordenada" onClose={onClose}>
      <div className="padded export-dialog">
        <p className="muted">
          Crea una <strong>copia</strong> de la carpeta de la empresa con el orden virtual (CFDI por mes, impuestos por
          periodo, IMSS por mes…). Tus archivos originales no se mueven ni se modifican, y nunca se sobrescribe nada.
          La e.firma, el sello digital y las contraseñas no se exportan.
        </p>
        {blockedReason && <p className="tax-why revisar">{blockedReason}</p>}
        <Field label="Carpeta de destino (nueva, dentro de una carpeta autorizada)">
          <input
            value={destination}
            placeholder="C:\Exportaciones\Mi empresa"
            onChange={(e) => setDestination(e.target.value)}
            disabled={busy || active}
          />
        </Field>
        <fieldset className="export-sections" disabled={busy || active}>
          <legend>Qué incluir</legend>
          {Object.entries(SECTIONS).map(([key, label]) => (
            <label key={key}>
              <input type="checkbox" checked={include.includes(key)} onChange={() => toggle(key)} /> {label}
            </label>
          ))}
          {include.includes('trabajadores') && (
            <p className="tax-why">Incluye identificaciones y datos de seguridad social: cuida dónde guardas esta copia.</p>
          )}
        </fieldset>
        {error && (
          <p role="alert" className="error-banner">
            {error}
          </p>
        )}
        {active && (
          <p role="status" aria-live="polite">
            Tu agente está trabajando… No cierres el agente hasta que termine.
          </p>
        )}
        {job?.status === 'failed' && !busy && (
          <p role="alert" className="error-banner">
            {result?.error || 'La operación falló.'}
          </p>
        )}
        {preview && (
          <section className="folder-analysis" aria-label="Vista previa de la exportación">
            <h3>Vista previa</h3>
            <p>
              {preview.total?.toLocaleString('es-MX')} archivos · {size(preview.bytes ?? 0)}
              {preview.free_bytes != null && ` · espacio libre ${size(preview.free_bytes)}`}
            </p>
            {preview.enough_space === false && <p className="tax-why revisar">No hay espacio suficiente en el destino.</p>}
            {preview.truncated && (
              <p className="tax-why revisar">El recorrido llegó a su límite: la copia saldría incompleta y no se permitirá.</p>
            )}
            <ul className="imss-files">
              {Object.entries(preview.sections ?? {}).map(([key, s]) => (
                <li key={key}>
                  <strong>{SECTIONS[key] ?? key}</strong> · {s.files} archivos · {size(s.bytes)} · {s.folders} carpetas
                  <small>{s.sample[0]}</small>
                </li>
              ))}
            </ul>
            {Object.keys(preview.excluded ?? {}).length > 0 && (
              <p className="muted">
                No se exportan:{' '}
                {Object.entries(preview.excluded ?? {})
                  .map(([k, n]) => `${n} de ${EXCLUDED[k] ?? k}`)
                  .join(', ')}
                .
              </p>
            )}
            {Object.keys(preview.omitted ?? {}).length > 0 && (
              <p className="muted">
                Fuera de la selección:{' '}
                {Object.entries(preview.omitted ?? {})
                  .map(([k, n]) => `${n} de ${SECTIONS[k] ?? k}`)
                  .join(', ')}
                .
              </p>
            )}
            {(preview.collisions ?? 0) > 0 && (
              <p className="muted">
                {preview.collisions} archivos comparten nombre y lugar: si son idénticos se omiten, y si no se numeran.
              </p>
            )}
          </section>
        )}
        {done && (
          <section className="folder-analysis" aria-label="Resultado de la exportación">
            <h3>Exportación terminada</h3>
            <p>
              {done.copiados} copiados · {done.duplicados} duplicados idénticos · {done.errores} con error ·{' '}
              {size(done.bytes ?? 0)}
            </p>
            <p className="muted">
              Carpeta: <code>{done.destination}</code>. El manifiesto <code>{done.manifiesto}</code> lista cada archivo con
              su ruta original, su ruta nueva y su huella SHA-256.
            </p>
            {(done.detalle_errores ?? []).map((e) => (
              <small className="tax-why revisar" key={e.p} title={e.p}>
                {e.p.split('/').pop()}: {e.motivo}
              </small>
            ))}
          </section>
        )}
        <div className="form-footer">
          <button className="btn" onClick={onClose}>
            Cerrar
          </button>
          <button className="btn" disabled={busy || active || !agentReady || !destination.trim() || !include.length} onClick={() => void send(false)}>
            Ver vista previa
          </button>
          <button
            className="btn primary"
            disabled={busy || active || !preview || preview.enough_space === false || !!preview.truncated}
            onClick={() => void send(true)}
          >
            Exportar copia
          </button>
        </div>
      </div>
    </Modal>
  );
}
