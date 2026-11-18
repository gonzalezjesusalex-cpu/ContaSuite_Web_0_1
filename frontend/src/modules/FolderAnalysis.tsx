import { FolderSearch, LoaderCircle } from 'lucide-react';
import { dateLabel } from '../api';
import type { Job } from '../types';

function size(bytes: number) {
  if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  return Math.max(1, Math.round(bytes / 1024)) + ' KB';
}

/** Result of «Analizar carpeta» grouped by document type, visible from every tab of the expediente. */
export default function FolderAnalysis({ job }: { job?: Job }) {
  if (!job) return null;
  if (job.status === 'queued' || job.status === 'running')
    return (
      <section className="folder-analysis" role="status" aria-live="polite">
        <p>
          <LoaderCircle size={16} className="spin" aria-hidden="true" />{' '}
          {job.status === 'queued'
            ? 'Análisis en cola: esperando a tu agente…'
            : 'Tu agente está clasificando los archivos de la carpeta…'}
        </p>
      </section>
    );
  const summary = job.result.summary;
  if (job.status !== 'completed' || !summary) return null;
  return (
    <section className="folder-analysis" aria-label="Clasificación de la carpeta">
      <header>
        <h3>
          <FolderSearch size={17} aria-hidden="true" /> Clasificación de la carpeta
        </h3>
        <small>
          {summary.total.toLocaleString('es-MX')} archivos · {size(summary.bytes)} · {dateLabel(job.created_at)}
        </small>
      </header>
      {job.result.truncated && <p className="muted">Se alcanzó el límite de recorrido: el conteo puede estar incompleto.</p>}
      <div className="folder-groups">
        {summary.groups.map((g) => (
          <details key={g.key} className={g.sensitive ? 'folder-group sensitive' : 'folder-group'}>
            <summary>
              <strong>{g.label}</strong>
              <span>
                {g.count.toLocaleString('es-MX')} · {size(g.bytes)}
              </span>
            </summary>
            <p className="muted">
              {Object.entries(g.extensions)
                .map(([ext, n]) => ext + ' ×' + n)
                .join(' · ')}
            </p>
            {Object.keys(g.subgroups).length > 0 && (
              <p>
                {Object.entries(g.subgroups)
                  .map(([name, n]) => name + ': ' + n)
                  .join(' · ')}
              </p>
            )}
            {g.sensitive ? (
              <p className="muted">Sólo se cuentan: no se abren ni se muestran sus nombres.</p>
            ) : (
              <ul>
                {g.examples.map((path) => (
                  <li key={path} title={path}>
                    {path}
                  </li>
                ))}
              </ul>
            )}
          </details>
        ))}
      </div>
      {job.result.warnings?.map((w, i) => (
        <p className="muted" key={i}>
          {w}
        </p>
      ))}
    </section>
  );
}
