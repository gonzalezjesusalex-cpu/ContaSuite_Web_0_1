import { useEffect, useState } from 'react';
import { ArrowRight, Download, FileText, RefreshCw, Undo2 } from 'lucide-react';
import { api, dateLabel, downloadApi } from '../../api';
import { Badge, Empty, Modal } from '../../components/ui';
import { stitchButton, stitchCard, stitchPrimary } from '../../components/stitch';
import { lockText } from './folderJobs';
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
  add('Leídos', 'leidos');
  add('Renombrados', 'renombrados');
  add('Restaurados', 'restaurados');
  add('Respaldo', 'carpeta');
  add('Error', 'error');
  if (Array.isArray(detail.pendientes) && detail.pendientes.length)
    parts.push(`Pendientes · en uso: ${detail.pendientes.join(', ')}`);
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

/** Paso 3: plan de nombres; en modo subir, copias verificadas; en modo carpeta, renombrado en la carpeta. */
export default function StepApply({
  detail,
  busy,
  logVersion,
  backup,
  onGenerate,
  onDownload,
  onApply,
  onUndo,
}: {
  detail: Detail;
  busy: boolean;
  logVersion: number;
  backup: boolean;
  onGenerate: () => Promise<void>;
  onDownload: (kind: 'zip' | 'csv') => void;
  onApply: (backup: boolean) => Promise<void>;
  onUndo: () => Promise<void>;
}) {
  const [confirm, setConfirm] = useState<'' | 'generar' | 'aplicar' | 'deshacer'>('');
  const { run, records } = detail;
  const s = run.summary;
  const folder = run.mode === 'carpeta';
  const plan = records.filter((r) => r.status === 'RENOMBRAR');
  const copies = (s.rename || 0) + (s.correct || 0);
  const generated = run.status === 'generated';
  const applied = run.status === 'applied';
  const working = ['generating', 'editing', 'analyzing', 'applying', 'undoing'].includes(run.status);
  const automatic = plan.filter((r) => r.origin !== 'manual').length;
  const longNames = folder
    ? plan.filter((r) => (run.folder_path || '').length + 1 + (r.expected_name || '').length > 240)
    : [];
  const counts: [string, number][] = [
    ['Automáticos', automatic],
    ['Manuales', plan.length - automatic],
    ['Ya correctos', s.correct || 0],
    ['Copias idénticas', s.identical || 0],
    ['Omitidos o con error', (s.omitted || 0) + (s.rfc_other || 0)],
    ['Excluidos', s.excluded_manual || 0],
  ];
  const lock = s.bloqueo;
  const readOnly = !!s.solo_lectura;
  return (
    <>
      <section className={stitchCard + ' padded'}>
        <div className="receipt-section-title">
          <h2>Plan de nombres</h2>
          <Badge tone={generated || applied ? 'green' : 'blue'}>
            {generated
              ? `${s.output || 0} copias verificadas`
              : applied
                ? `${s.renamed || 0} archivos renombrados`
                : `${plan.length} archivos por renombrar`}
          </Badge>
        </div>
        {folder && (
          <div className="declara-tags">
            {backup && <Badge tone="green">Respaldo de originales activado</Badge>}
            {lock?.estado === 'propio' && (
              <Badge tone="blue">Carpeta bloqueada por ti · {lock.equipo || s.equipo}</Badge>
            )}
            {readOnly && <Badge tone="red">{lockText(lock)}</Badge>}
          </div>
        )}
        <ul className="declara-plan-summary">
          {counts.map(([label, n]) => (
            <li key={label}>
              <strong>{n}</strong>
              <span>{label}</span>
            </li>
          ))}
        </ul>
        <p className="muted">
          {folder
            ? `Se renombra en la carpeta ${run.folder_path}. Los omitidos, copias idénticas y excluidos no se tocan.`
            : 'Se trabaja con copias: los originales no se tocan. Los omitidos, copias idénticas y excluidos no se incluyen en el ZIP.'}
        </p>
        {longNames.length > 0 && (
          <p className="declara-msg warn">
            {longNames.length} destinos pasan de 240 caracteres con la ruta: se usarán rutas largas de Windows.
          </p>
        )}
        {(s.pendientes || []).length > 0 && (
          <p className="declara-msg warn">
            Pendiente · en uso por otro usuario: {(s.pendientes || []).join(', ')}. Vuelve a analizar cuando se liberen.
          </p>
        )}
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
          {folder ? (
            <>
              <button
                type="button"
                className={stitchPrimary}
                disabled={busy || working || applied || !plan.length || !s.rfc_matches || readOnly}
                onClick={() => setConfirm('aplicar')}
              >
                {run.status === 'applying' ? (
                  <RefreshCw size={16} className="recopila-spinner" />
                ) : (
                  <FileText size={16} />
                )}
                {run.status === 'applying' ? 'Aplicando…' : 'Aplicar renombrado en la carpeta'}
              </button>
              <button
                type="button"
                className={stitchButton}
                disabled={busy || working || !s.deshacer || readOnly}
                onClick={() => setConfirm('deshacer')}
              >
                <Undo2 size={16} />
                {run.status === 'undoing' ? 'Deshaciendo…' : 'Deshacer último renombrado'}
              </button>
            </>
          ) : !generated ? (
            <button
              type="button"
              className={stitchPrimary}
              disabled={busy || working || !copies || !s.rfc_matches}
              onClick={() => setConfirm('generar')}
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
          <p className="declara-msg error">El RFC detectado no coincide con la empresa: no se renombra nada.</p>
        )}
      </section>
      <Log companyId={run.company_id} year={s.year || run.year || new Date().getFullYear()} version={logVersion} />
      {confirm === 'generar' && (
        <Modal title="Generar copias renombradas" onClose={() => setConfirm('')}>
          <div className="declara-modal-body">
            <p>
              Se generarán {copies} copias verificadas ({plan.length} con nombre nuevo) en un ZIP para{' '}
              <strong>{run.short_name}</strong>. Los PDF originales no se modifican.
            </p>
            <Confirm label="Generar copias" onCancel={() => setConfirm('')} onOk={onGenerate} done={setConfirm} />
          </div>
        </Modal>
      )}
      {confirm === 'aplicar' && (
        <Modal title="Aplicar renombrado en la carpeta" onClose={() => setConfirm('')}>
          <div className="declara-modal-body">
            <p>
              Se renombrarán <strong>{plan.length} archivos</strong> en <code>{run.folder_path}</code>.
              {backup ? ' Antes se respaldan los originales en .declara\\respaldos.' : ' Sin respaldo de originales.'}{' '}
              Nunca se sobrescribe un archivo y el lote queda registrado para deshacerlo.
            </p>
            <Confirm
              label="Aplicar renombrado"
              onCancel={() => setConfirm('')}
              onOk={() => onApply(backup)}
              done={setConfirm}
            />
          </div>
        </Modal>
      )}
      {confirm === 'deshacer' && (
        <Modal title="Deshacer último renombrado" onClose={() => setConfirm('')}>
          <div className="declara-modal-body">
            <p>
              Se devolverán a su nombre anterior los archivos del último lote aplicado en <code>{run.folder_path}</code>
              .
            </p>
            <Confirm label="Deshacer" onCancel={() => setConfirm('')} onOk={onUndo} done={setConfirm} />
          </div>
        </Modal>
      )}
    </>
  );
}

function Confirm({
  label,
  onCancel,
  onOk,
  done,
}: {
  label: string;
  onCancel: () => void;
  onOk: () => Promise<void>;
  done: (v: '') => void;
}) {
  return (
    <div className="actions">
      <button type="button" className={stitchButton} onClick={onCancel}>
        Cancelar
      </button>
      <button
        type="button"
        className={stitchPrimary}
        onClick={() => {
          done('');
          void onOk();
        }}
      >
        {label}
      </button>
    </div>
  );
}
