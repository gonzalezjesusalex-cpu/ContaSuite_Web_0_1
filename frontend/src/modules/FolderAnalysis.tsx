import { FolderSearch, LoaderCircle } from 'lucide-react';
import { dateLabel } from '../api';
import type { Job } from '../types';

function ReanalyzeButton({
  onClick,
  disabled,
  analyzing,
}: {
  onClick: () => void;
  disabled?: boolean;
  analyzing?: boolean;
}) {
  return (
    <button type="button" className="btn" disabled={disabled} onClick={onClick}>
      <FolderSearch size={15} aria-hidden="true" />
      {analyzing ? 'Analizando…' : 'Volver a analizar'}
    </button>
  );
}

function size(bytes: number) {
  if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  return Math.max(1, Math.round(bytes / 1024)) + ' KB';
}

/** One-line status shown in the header of the expediente (cambio 1.1): the detail lives in the Documentos tab. */
export function FolderAnalysisLine({ job, doneJob, onView }: { job?: Job; doneJob?: Job; onView: () => void }) {
  if (job && (job.status === 'queued' || job.status === 'running'))
    return (
      <p className="folder-analysis-line" role="status" aria-live="polite">
        <LoaderCircle size={15} className="spin" aria-hidden="true" />{' '}
        {job.status === 'queued' ? 'Análisis en cola…' : 'Clasificando…'}
      </p>
    );
  const done = doneJob?.result.summary ? doneJob : job?.status === 'completed' && job.result.summary ? job : undefined;
  if (!done?.result.summary) return null;
  return (
    <p className="folder-analysis-line">
      <FolderSearch size={15} aria-hidden="true" /> Última clasificación:{' '}
      {done.result.summary.total.toLocaleString('es-MX')} archivos · {dateLabel(done.created_at)} ·{' '}
      <button type="button" className="link-button" onClick={onView}>
        Ver
      </button>
    </p>
  );
}

/** Full result of «Analizar carpeta» grouped by document type: the «Clasificación de carpeta» tab (cambio 1.2). */
export default function FolderAnalysis({
  job,
  onReanalyze,
  reanalyzeDisabled,
  analyzing,
}: {
  job?: Job;
  onReanalyze?: () => void;
  reanalyzeDisabled?: boolean;
  analyzing?: boolean;
}) {
  if (!job)
    return (
      <p className="muted">
        Aún no hay una clasificación de la carpeta.{' '}
        {onReanalyze && <ReanalyzeButton onClick={onReanalyze} disabled={reanalyzeDisabled} analyzing={analyzing} />}
      </p>
    );
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
  if (job.status !== 'completed' || !summary)
    return (
      <p className="muted">
        El último análisis no produjo clasificación.{' '}
        {onReanalyze && <ReanalyzeButton onClick={onReanalyze} disabled={reanalyzeDisabled} analyzing={analyzing} />}
      </p>
    );
  return (
    <section className="folder-analysis" aria-label="Clasificación de la carpeta">
      <header>
        <h3>
          <FolderSearch size={17} aria-hidden="true" /> Clasificación de la carpeta
        </h3>
        <small>
          {summary.total.toLocaleString('es-MX')} archivos · {size(summary.bytes)} · Último análisis:{' '}
          {dateLabel(job.created_at)}
        </small>
        {onReanalyze && <ReanalyzeButton onClick={onReanalyze} disabled={reanalyzeDisabled} analyzing={analyzing} />}
      </header>
      {job.result.truncated && (
        <p className="muted">Se alcanzó el límite de recorrido: el conteo puede estar incompleto.</p>
      )}
      {job.result.incomplete && !job.result.truncated && (
        <p className="muted" role="alert">
          El recorrido quedó incompleto (carpetas o archivos sin acceso): el conteo puede ser menor al real y no se
          marcaron archivos como faltantes.
        </p>
      )}
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
