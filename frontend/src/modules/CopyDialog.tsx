import { useState } from 'react';
import { api } from '../api';
import { Modal } from '../components/ui';
import type { Company, Job } from '../types';

const SECTIONS: Record<string, string> = {
  cfdi: 'CFDI',
  impuestos: 'Impuestos',
  imss: 'IMSS',
  nomina: 'Nómina',
  expediente: 'Expediente de la empresa',
  finanzas: 'Estados financieros',
  sin_clasificar: 'Sin clasificar',
  trabajadores: 'Trabajadores (datos personales)',
};
const DEFAULT_ON = ['cfdi', 'impuestos', 'imss', 'nomina', 'expediente', 'finanzas'];

/** Analyze the folder and store an internal copy of the content inside ContaSuite. Originals are never touched. */
export default function CopyDialog({
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
  const [include, setInclude] = useState<string[]>(DEFAULT_ON);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const job = jobs.find((j) => j.kind === 'scan_folder');
  const active = !!job && (job.status === 'queued' || job.status === 'running');
  const copia = job?.status === 'completed' ? job.result.copia : undefined;
  const toggle = (key: string) =>
    setInclude((list) => (list.includes(key) ? list.filter((k) => k !== key) : [...list, key]));
  async function start() {
    setBusy(true);
    setError('');
    try {
      await api('/jobs', 'POST', { company_id: company.id, kind: 'scan_folder', copy: include });
      await refresh();
      notify('Análisis con copia interna enviado a tu agente.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Guardar copia interna" onClose={onClose}>
      <div className="padded export-dialog">
        <p className="muted">
          Analiza la carpeta y guarda dentro de ContaSuite una <strong>copia del contenido</strong> de los archivos
          elegidos. Si después un original se mueve, se renombra o se borra, la copia sigue disponible. Tus originales
          no se tocan. Cada contenido se guarda una sola vez, identificado por su huella SHA-256. La e.firma, las llaves
          y las contraseñas nunca se copian, y los archivos de más de 25 MB se omiten.
        </p>
        {blockedReason && <p className="tax-why revisar">{blockedReason}</p>}
        <fieldset className="export-sections" disabled={busy || active}>
          <legend>Qué copiar</legend>
          {Object.entries(SECTIONS).map(([key, label]) => (
            <label key={key}>
              <input type="checkbox" checked={include.includes(key)} onChange={() => toggle(key)} /> {label}
            </label>
          ))}
          {include.includes('trabajadores') && (
            <p className="tax-why">
              Incluye identificaciones y datos de seguridad social: quedarán guardados en el servidor de ContaSuite.
            </p>
          )}
        </fieldset>
        {error && (
          <p role="alert" className="error-banner">
            {error}
          </p>
        )}
        {active && (
          <p role="status" aria-live="polite">
            Tu agente está analizando y copiando… No cierres el agente hasta que termine.
          </p>
        )}
        {job?.status === 'failed' && !busy && (
          <p role="alert" className="error-banner">
            {job.result.error || 'La operación falló.'}
          </p>
        )}
        {copia && !busy && (
          <section className="folder-analysis" aria-label="Resultado de la copia">
            <h3>Copia terminada</h3>
            <p>
              {copia.archivos} archivos elegidos · {copia.subidos} copiados ahora · {copia.ya_estaban} ya estaban
              guardados
              {copia.errores > 0 && ` · ${copia.errores} con error`}
              {copia.sin_huella > 0 && ` · ${copia.sin_huella} omitidos (muy grandes o ilegibles)`}
            </p>
            {copia.error && <p className="tax-why revisar">{copia.error}</p>}
            <p className="muted">
              Los archivos con copia aparecen en el Inventario › Cambios y faltantes, donde puedes abrirlos aunque el
              original ya no exista.
            </p>
          </section>
        )}
        <div className="form-footer">
          <button className="btn" onClick={onClose}>
            Cerrar
          </button>
          <button
            className="btn primary"
            disabled={busy || active || !agentReady || !include.length}
            onClick={() => void start()}
          >
            Analizar y guardar copia
          </button>
        </div>
      </div>
    </Modal>
  );
}
