import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, dateLabel } from '../api';
import { stitchButton } from '../components/stitch';
import { INCOHERENCE } from './CfdiExpediente';
import { periodLabel } from './RecopilaReview';

export type CfdiPending = {
  id: string;
  run_id: string;
  name: string;
  kind: string;
  state: string;
  reasons: string[];
  folder_period: string;
  xml_period: string | null;
};
export type CfdiPeriod = { period: string; xml: number; pdf: number; reports?: number; en_revision: number };
export type CfdiReviewData = { pending: CfdiPending[]; periods: CfdiPeriod[] };

/** Files of the company's saved CFDI by period and those waiting for a person; `null` without CFDI access. */
export function useCfdiReview(companyId?: string, reload = 0, version = 0) {
  const [data, setData] = useState<CfdiReviewData | null>(null);
  useEffect(() => {
    setData(null);
    if (!companyId) return;
    const abort = new AbortController();
    api<CfdiReviewData>('/organizador/companies/' + companyId + '/review', 'GET', undefined, abort.signal)
      .then(setData)
      .catch(() => undefined);
    return () => abort.abort();
  }, [companyId, reload, version]);
  return data;
}

/** «CFDI Oct 2026: 120 XML · 118 PDF · 3 en revisión» (informative, cambio 5.6). */
export function CfdiIndicator({ data }: { data: CfdiReviewData | null }) {
  if (!data?.periods.length) return null;
  return (
    <ul className="recopila-indicator" aria-label="CFDI guardados por periodo">
      {data.periods.slice(0, 4).map((p) => (
        <li key={p.period}>
          CFDI {periodLabel(p.period)}: {p.xml} XML · {p.pdf} PDF
          {p.reports ? ` · ${p.reports} ${p.reports === 1 ? 'reporte' : 'reportes'}` : ''} · {p.en_revision} en revisión
        </li>
      ))}
    </ul>
  );
}

const reasonText = (r: string) => INCOHERENCE[r] || r;

/** «Por revisar › CFDI»: blocked or conflicting files. Only a period disagreement can be saved by the reviewer. */
export function CfdiReviewSection({ data, onChanged }: { data: CfdiReviewData | null; onChanged: () => void }) {
  const [error, setError] = useState('');
  const [choice, setChoice] = useState<Record<string, 'folder' | 'xml'>>({});
  if (!data) return <p role="status">Consultando archivos CFDI en revisión…</p>;
  async function resolve(id: string, action: 'save' | 'dismiss') {
    setError('');
    try {
      await api('/organizador/items/' + id + '/resolve', 'POST', { action, period: choice[id] || 'folder' });
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section aria-labelledby="cfdi-review-title">
      <h3 id="cfdi-review-title">CFDI</h3>
      <p>
        Archivos que no se guardaron solos: incoherencia entre carpeta y contenido, o conflicto con lo ya registrado. Si
        la carpeta y el XML discrepan en el periodo, decides cuál usar y queda registrado con tu usuario y fecha.
      </p>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {data.pending.length === 0 ? (
        <p className="muted">Sin archivos CFDI por revisar.</p>
      ) : (
        <ul>
          {data.pending.map((p) => {
            const periodOnly = p.reasons.length > 0 && p.reasons.every((r) => r === 'periodo_distinto');
            return (
              <li key={p.id}>
                <strong>{p.name}</strong> · {p.kind} · carpeta {p.folder_period}
                {p.xml_period && ' · XML ' + p.xml_period} · {p.reasons.map(reasonText).join(', ') || 'en revisión'}{' '}
                <Link to={'/organizador-cfdi?analisis=' + p.run_id}>Abrir análisis</Link>
                {periodOnly && (
                  <select
                    aria-label={'Periodo para ' + p.name}
                    value={choice[p.id] || 'folder'}
                    onChange={(e) => setChoice({ ...choice, [p.id]: e.target.value as 'folder' | 'xml' })}
                  >
                    <option value="folder">Usar el de la carpeta ({p.folder_period})</option>
                    <option value="xml">Usar el del XML ({p.xml_period})</option>
                  </select>
                )}{' '}
                {periodOnly && (
                  <button className={stitchButton} onClick={() => void resolve(p.id, 'save')}>
                    Guardar con ese periodo
                  </button>
                )}
                <button className={stitchButton} onClick={() => void resolve(p.id, 'dismiss')}>
                  Descartar
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

type RunRow = { id: string; company_id: string | null; name: string; status: string; created_at: string };
const RUN_STATE: Record<string, string> = {
  analyzing: 'Analizando',
  analyzed: 'Listo para revisar',
  generating: 'Organizando',
  generated: 'Terminado',
  error: 'Con error',
};

/** CFDI analyses of the company, shown in the «Actividad» tab (cambio 5.6). */
export function CfdiRuns({ companyId }: { companyId: string }) {
  const [runs, setRuns] = useState<RunRow[] | null>(null);
  useEffect(() => {
    setRuns(null);
    const abort = new AbortController();
    api<RunRow[]>('/organizador/runs', 'GET', undefined, abort.signal)
      .then((all) => setRuns(all.filter((r) => r.company_id === companyId)))
      .catch(() => setRuns([]));
    return () => abort.abort();
  }, [companyId]);
  if (!runs?.length) return null;
  return (
    <section className="card padded" aria-labelledby="cfdi-runs-title">
      <h2 id="cfdi-runs-title">Corridas de CFDI</h2>
      <ul>
        {runs.map((r) => (
          <li key={r.id}>
            <Link to={'/organizador-cfdi?empresa=' + companyId + '&analisis=' + r.id}>{r.name}</Link> ·{' '}
            {RUN_STATE[r.status] || r.status} · {dateLabel(r.created_at)}
          </li>
        ))}
      </ul>
    </section>
  );
}
