import { useEffect, useState } from 'react';
import { ArrowRight, Download, FileText, RefreshCw } from 'lucide-react';
import { api, dateLabel, downloadApi } from '../../api';
import { Badge, Empty, Modal } from '../../components/ui';
import { stitchButton, stitchCard, stitchPrimary } from '../../components/stitch';
import { fileName, type Detail, type LogEntry } from './model';

function describe(detail: Record<string, unknown>) {
  const parts: string[] = [];
  const add = (label: string, key: string) =>
    detail[key] !== undefined && parts.push(`${label}: ${String(detail[key])}`);
  if (detail.archivo) parts.push(String(detail.archivo));
  if (detail.antes !== undefined || detail.despues !== undefined)
    parts.push(`${detail.antes || '—'} → ${detail.despues || '—'}`);
  add('PDF', 'pdf');
  add('Por renombrar', 'por_renombrar');
  add('Correctos', 'correctos');
  add('Copias idénticas', 'copias_identicas');
  add('Omitidos', 'omitidos');
  add('Copias', 'copias');
  add('Manuales', 'manuales');
  if (detail.cuenta === false) parts.push('No cuenta en el control');
  return parts.join(' · ');
}

/** Bitácora de la empresa y el ejercicio, con exportación CSV. */
export function Log({ companyId, year, version }: { companyId: string; year: number; version: number }) {
  const [entries, setEntries] = useState<LogEntry[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    api<LogEntry[]>(`/declara/log?company_id=${encodeURIComponent(companyId)}&year=${year}`)
      .then((r) => active && setEntries(r))
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [companyId, year, version]);
  return (
    <section className={stitchCard + ' padded declara-log'}>
      <div className="receipt-section-title">
        <h2>Bitácora</h2>
        <button
          type="button"
          className={stitchButton}
          disabled={!entries?.length}
          onClick={() =>
            downloadApi(
              `/declara/log.csv?company_id=${encodeURIComponent(companyId)}&year=${year}`,
              `BITACORA_DECLARA_${year}.csv`,
            ).catch((e) => setError(e.message))
          }
        >
          <Download size={15} />
          Exportar
        </button>
      </div>
      {error && <p className="declara-msg error">{error}</p>}
      {entries && !entries.length && <Empty title="Sin movimientos">Aún no hay acciones registradas.</Empty>}
      <ol className="declara-log-list">
        {(entries || []).map((e) => (
          <li key={e.id}>
            <div>
              <strong>{e.label}</strong>
              <small>
                {dateLabel(e.created_at)} · {new Date(e.created_at).toLocaleTimeString('es-MX', { timeStyle: 'short' })}{' '}
                · {e.user}
                {e.machine ? ' · ' + e.machine : ''}
              </small>
            </div>
            <p>{describe(e.detail)}</p>
            {e.path && <p className="declara-mono">{e.path}</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Paso 3 en modo subir: plan, copias renombradas verificadas, descargas y bitácora. */
export default function StepApply({
  detail,
  busy,
  logVersion,
  onGenerate,
  onDownload,
}: {
  detail: Detail;
  busy: boolean;
  logVersion: number;
  onGenerate: () => Promise<void>;
  onDownload: (kind: 'zip' | 'csv') => void;
}) {
  const [confirm, setConfirm] = useState(false);
  const { run, records } = detail;
  const s = run.summary;
  const plan = records.filter((r) => r.status === 'RENOMBRAR');
  const copies = (s.rename || 0) + (s.correct || 0);
  const generated = run.status === 'generated';
  const working = ['generating', 'editing', 'analyzing'].includes(run.status);
  const automatic = plan.filter((r) => r.origin !== 'manual').length;
  const counts: [string, number][] = [
    ['Automáticos', automatic],
    ['Manuales', plan.length - automatic],
    ['Ya correctos', s.correct || 0],
    ['Copias idénticas', s.identical || 0],
    ['Omitidos o con error', (s.omitted || 0) + (s.rfc_other || 0)],
    ['Excluidos', s.excluded_manual || 0],
  ];
  return (
    <>
      <section className={stitchCard + ' padded'}>
        <div className="receipt-section-title">
          <h2>Plan de nombres</h2>
          <Badge tone={generated ? 'green' : 'blue'}>
            {generated ? `${s.output || 0} copias verificadas` : `${plan.length} archivos por renombrar`}
          </Badge>
        </div>
        <ul className="declara-plan-summary">
          {counts.map(([label, n]) => (
            <li key={label}>
              <strong>{n}</strong>
              <span>{label}</span>
            </li>
          ))}
        </ul>
        <p className="muted">
          Se trabaja con copias: los originales no se tocan. Los omitidos, copias idénticas y excluidos no se incluyen
          en el ZIP.
        </p>
        {plan.length ? (
          <ol className="declara-plan">
            {plan.map((r) => (
              <li key={r.index}>
                <span>{fileName(r.path)}</span>
                <ArrowRight size={14} aria-hidden="true" />
                <strong>{r.expected_name}</strong>
                {r.origin === 'manual' && <Badge tone="blue">Manual</Badge>}
              </li>
            ))}
          </ol>
        ) : (
          <Empty title="Nada que renombrar">Todos los archivos reconocidos ya tienen el nombre estándar.</Empty>
        )}
        <div className="actions">
          {!generated ? (
            <button
              type="button"
              className={stitchPrimary}
              disabled={busy || working || !copies || !s.rfc_matches}
              onClick={() => setConfirm(true)}
            >
              {working ? <RefreshCw size={16} className="recopila-spinner" /> : <FileText size={16} />}
              {run.status === 'generating' ? 'Generando…' : `Generar ${copies} copias renombradas`}
            </button>
          ) : (
            <>
              <button type="button" className={stitchPrimary} disabled={busy} onClick={() => onDownload('zip')}>
                <Download size={16} />
                Descargar ZIP
              </button>
              <button type="button" className={stitchButton} disabled={busy} onClick={() => onDownload('csv')}>
                <Download size={16} />
                Auditoría CSV
              </button>
            </>
          )}
        </div>
        {!s.rfc_matches && (
          <p className="declara-msg error">El RFC detectado no coincide con la empresa: no se generan copias.</p>
        )}
      </section>
      <Log companyId={run.company_id} year={s.year || run.year || new Date().getFullYear()} version={logVersion} />
      {confirm && (
        <Modal title="Generar copias renombradas" onClose={() => setConfirm(false)}>
          <p>
            Se generarán {copies} copias verificadas ({plan.length} con nombre nuevo) en un ZIP para{' '}
            <strong>{run.short_name}</strong>. Los PDF originales no se modifican.
          </p>
          <div className="actions">
            <button type="button" className={stitchButton} onClick={() => setConfirm(false)}>
              Cancelar
            </button>
            <button
              type="button"
              className={stitchPrimary}
              onClick={() => {
                setConfirm(false);
                void onGenerate();
              }}
            >
              Generar copias
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
