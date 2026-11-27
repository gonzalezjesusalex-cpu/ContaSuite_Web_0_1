import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Check, Circle, Download, Pause, Play, RefreshCw, ShieldCheck, Square } from 'lucide-react';
import { api } from '../../api';
import { Badge, Empty } from '../../components/ui';
import { stitchButton, stitchCard, stitchDanger, stitchPrimary } from '../../components/stitch';
import { folderOp, type FolderJob } from './folderJobs';
import { MONTHS, longDate, monthLabel, type Run } from './model';

type SatStatus = {
  fiel: { disponible: boolean; rfc: string | null; vence: string | null };
  boveda_abierta: boolean;
  agente: { vinculado: boolean; en_linea: boolean; equipo: string | null };
  portal: boolean;
  persona: 'moral' | 'fisica';
};
type Browser = { playwright: boolean; firefox: boolean; portal: boolean; navegacion: string };
type Row = {
  fila: string;
  operacion: string;
  tipo: string;
  periodo: string;
  estado: string;
  motivo?: string;
  nombre?: string;
};
type Progress = {
  etapa?: string;
  etapas?: Record<string, string>;
  encontradas?: number;
  total?: number;
  procesadas?: number;
  guardadas?: number;
  ya_existian?: number;
  errores?: number;
  acceso?: string;
  filas?: Row[];
};
type SatResult = {
  progreso?: Progress;
  sesion?: Progress & { cancelada?: boolean };
  analisis_id?: string;
  pausar?: boolean;
  cancelar?: boolean;
};

const STAGES: [string, string][] = [
  ['agente', 'Agente conectado'],
  ['firefox', 'Firefox abierto'],
  ['sesion', 'Inicio de sesión'],
  ['consulta', 'Consulta de declaraciones'],
  ['descarga', 'Descargando faltantes'],
  ['reanalisis', 'Reanalizar carpeta'],
];

const ROW_STATES: Record<string, { label: string; tone: string }> = {
  en_cola: { label: 'En cola', tone: 'neutral' },
  descargando: { label: 'Descargando…', tone: 'blue' },
  guardado: { label: 'Guardado y renombrado', tone: 'green' },
  ya_existia: { label: 'Ya existía', tone: 'neutral' },
  error: { label: 'Error', tone: 'red' },
};

const REASONS: Record<string, string> = {
  tiempo_agotado: 'tiempo agotado 25 s',
  no_es_pdf: 'el SAT no entregó un PDF',
  sin_control: 'sin ícono PDF: no se hizo clic',
  descarga_fallida: 'no se pudo descargar',
  demasiado_grande: 'pasa de 25 MB',
  copia_no_verificada: 'la copia no coincide con su huella',
  carpeta_bloqueada: 'carpeta en uso por otra persona',
};

const PROTECTIONS = [
  'Descarga primero a una carpeta temporal local de este equipo.',
  'Valida que cada archivo empiece con %PDF-; lo demás se descarta.',
  'Una fila a la vez, con 25 s máximo por fila.',
  'Si no identifica el ícono PDF, se detiene y avisa: nada de clics a ciegas.',
  'Conserva normal y complementaria del mismo mes.',
  'Copia a la carpeta con nombre temporal, verifica tamaño y huella y renombra: nunca sobrescribe.',
];

/** Sesión SAT de Declara (4.4): la maneja el agente; aquí se elige qué descargar y se sigue la cola en vivo. */
export default function SatSession({
  run,
  initialPeriod,
  onBack,
  onFinished,
  notify,
}: {
  run: Run;
  initialPeriod: string;
  onBack: () => void;
  onFinished: (runId: string) => void;
  notify: (m: string) => void;
}) {
  const [status, setStatus] = useState<SatStatus | null>(null);
  const [browser, setBrowser] = useState<Browser | null>(null);
  const [method, setMethod] = useState<'fiel' | 'ciec'>('fiel');
  const [onlyMissing, setOnlyMissing] = useState(true);
  const [period, setPeriod] = useState(initialPeriod);
  const [jobId, setJobId] = useState('');
  const [job, setJob] = useState<FolderJob<SatResult> | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const loadStatus = useCallback(() => {
    api<SatStatus>(`/declara/companies/${encodeURIComponent(run.company_id)}/sat`)
      .then((s) => {
        setStatus(s);
        if (!s.fiel.disponible) setMethod('ciec');
      })
      .catch((e) => setError(e.message));
    folderOp<Browser>(run.company_id, 'sat_estado')
      .then(setBrowser)
      .catch(() => setBrowser(null));
  }, [run.company_id]);

  useEffect(loadStatus, [loadStatus]);

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const current = await api<FolderJob<SatResult>>('/declara/folder/jobs/' + jobId);
        if (!active) return;
        setJob(current);
        if (current.status === 'queued' || current.status === 'running') timer = setTimeout(tick, 1500);
        else if (current.status === 'completed') notify('Sesión SAT terminada: la carpeta se volvió a analizar.');
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    };
    void tick();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [jobId, notify]);

  async function start(periodOverride?: string) {
    setBusy('iniciar');
    setError('');
    try {
      const { job_id } = await api<{ job_id: string }>(`/declara/runs/${run.id}/sat`, 'POST', {
        metodo: method,
        solo_faltantes: onlyMissing,
        periodo: periodOverride ?? period,
      });
      setJob(null);
      setJobId(job_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function control(accion: string, operacion = '') {
    try {
      await api(`/declara/folder/jobs/${jobId}/control`, 'POST', { accion, operacion });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function install() {
    setBusy('instalar');
    try {
      setBrowser(await folderOp<Browser>(run.company_id, 'sat_instalar'));
      notify('Firefox del agente instalado.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  const running = job?.status === 'queued' || job?.status === 'running';
  const finished = job?.status === 'completed' || job?.status === 'failed';
  const progress: Progress = job?.result?.sesion || job?.result?.progreso || {};
  const stages = progress.etapas || {};
  const rows = progress.filas || [];
  const paused = !!job?.result?.pausar;
  const total = progress.total || 0;
  const done = progress.procesadas || 0;
  const accessText =
    method === 'fiel' ? 'Sesión con la e.firma del gestor' : 'Sesión con CIEC (el captcha lo resuelves tú)';
  return (
    <div className="declara-sat">
      <div className="declara-sat-head">
        <div>
          <h2>
            Sesión SAT · {run.short_name} · {run.expected_rfc}
          </h2>
          <p className="muted">Destino: {run.folder_path}</p>
        </div>
        <div className="actions">
          {running && (
            <button type="button" className={stitchButton} onClick={() => control(paused ? 'reanudar' : 'pausar')}>
              {paused ? <Play size={16} /> : <Pause size={16} />}
              {paused ? 'Reanudar' : 'Pausar'}
            </button>
          )}
          {running && (
            <button type="button" className={stitchDanger} onClick={() => control('detener')}>
              <Square size={16} />
              Detener sesión
            </button>
          )}
          <button type="button" className={stitchButton} onClick={onBack} disabled={running}>
            <ArrowLeft size={16} />
            Volver a revisión
          </button>
        </div>
      </div>
      {error && <p className="declara-msg error">{error}</p>}
      <div className="declara-step-grid">
        <div className="declara-step-main">
          <section className={stitchCard + ' padded'}>
            <ol className="declara-stages" aria-label="Etapas de la sesión">
              {STAGES.map(([key, label]) => {
                const state = key === 'agente' && (running || finished) ? 'hecho' : stages[key] || 'pendiente';
                const text =
                  key === 'sesion'
                    ? accessText
                    : key === 'consulta' && progress.encontradas != null
                      ? `${label} (${progress.encontradas} encontradas)`
                      : label;
                return (
                  <li key={key} className={'declara-stage ' + state}>
                    {state === 'hecho' ? (
                      <Check size={15} aria-hidden="true" />
                    ) : state === 'en_curso' ? (
                      <RefreshCw size={15} className="recopila-spinner" aria-hidden="true" />
                    ) : (
                      <Circle size={15} aria-hidden="true" />
                    )}
                    <span>{text}</span>
                  </li>
                );
              })}
            </ol>
          </section>

          <section className={stitchCard + ' padded'}>
            <div className="receipt-section-title">
              <h2>Cola de descarga</h2>
              {running && <Badge tone={paused ? 'amber' : 'blue'}>{paused ? 'Pausada' : 'En curso'}</Badge>}
              {finished && (
                <Badge tone={job?.status === 'completed' ? 'green' : 'red'}>
                  {job?.status === 'completed' ? 'Terminada' : 'Con error'}
                </Badge>
              )}
            </div>
            {!jobId && (
              <div className="declara-sat-options">
                <label className="declara-check">
                  <input type="checkbox" checked={onlyMissing} onChange={(e) => setOnlyMissing(e.target.checked)} />
                  Solo faltantes (compara los números de operación con la carpeta)
                </label>
                <label>
                  Periodo
                  <select value={period} onChange={(e) => setPeriod(e.target.value)}>
                    <option value="">Todo el ejercicio {run.year}</option>
                    {MONTHS.map((m, i) => (
                      <option key={m} value={m}>
                        {i + 1}. {monthLabel(m)}
                      </option>
                    ))}
                  </select>
                </label>
                <fieldset className="declara-sat-method">
                  <legend>Inicio de sesión</legend>
                  <label>
                    <input
                      type="radio"
                      name="sat-method"
                      checked={method === 'fiel'}
                      disabled={!status?.fiel.disponible}
                      onChange={() => setMethod('fiel')}
                    />
                    e.firma del gestor de contraseñas
                  </label>
                  <label>
                    <input
                      type="radio"
                      name="sat-method"
                      checked={method === 'ciec'}
                      onChange={() => setMethod('ciec')}
                    />
                    CIEC (escribes tú los datos y resuelves el captcha en Firefox)
                  </label>
                </fieldset>
                <button
                  type="button"
                  className={stitchPrimary}
                  disabled={!!busy || !status?.portal || !status.agente.en_linea}
                  onClick={() => void start()}
                >
                  <Download size={16} />
                  {busy === 'iniciar' ? 'Preparando…' : 'Iniciar sesión SAT'}
                </button>
              </div>
            )}
            {jobId && (
              <>
                <div
                  className="declara-progress"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={total || 1}
                  aria-valuenow={done}
                  aria-label="Avance de la cola"
                >
                  <span style={{ width: `${total ? Math.round((done / total) * 100) : 0}%` }} />
                </div>
                <ul className="declara-plan-summary">
                  <li>
                    <strong>
                      {done}/{total}
                    </strong>
                    <span>Procesadas</span>
                  </li>
                  <li>
                    <strong>{progress.guardadas ?? 0}</strong>
                    <span>Guardadas y renombradas</span>
                  </li>
                  <li>
                    <strong>{progress.ya_existian ?? 0}</strong>
                    <span>Ya existían (se omiten)</span>
                  </li>
                  <li>
                    <strong>{progress.errores ?? 0}</strong>
                    <span>Errores</span>
                  </li>
                </ul>
                {job?.status === 'failed' && (
                  <p className="declara-msg error">
                    {(job.result as { error?: string }).error || 'La sesión no se pudo completar.'}
                  </p>
                )}
                {progress.etapa === 'esperando_sesion' && running && (
                  <p className="declara-banner">
                    {progress.acceso === 'fiel'
                      ? 'Se envió la e.firma a la ventana de Firefox. Si el SAT pide algo más, termina el inicio de sesión ahí.'
                      : 'Inicia sesión en la ventana de Firefox que se abrió y llega a «Consulta de declaraciones».'}
                  </p>
                )}
                <div className="declara-table-scroll">
                  <table className="declara-table declara-sat-table">
                    <thead>
                      <tr>
                        <th>Periodo</th>
                        <th>Tipo</th>
                        <th>Nº operación</th>
                        <th>Estado</th>
                        <th>
                          <span className="sr-only">Acción</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => {
                        const state = ROW_STATES[r.estado] || { label: r.estado, tone: 'neutral' };
                        return (
                          <tr key={r.fila + r.operacion}>
                            <td>{r.periodo}</td>
                            <td>{r.tipo}</td>
                            <td className="declara-mono">{r.operacion || '—'}</td>
                            <td>
                              <Badge tone={state.tone}>
                                {state.label}
                                {r.estado === 'error' && r.motivo ? ' · ' + (REASONS[r.motivo] || r.motivo) : ''}
                              </Badge>
                              {r.nombre && <small className="declara-mono">{r.nombre}</small>}
                            </td>
                            <td className="declara-row-actions">
                              {r.estado === 'error' && (
                                <button
                                  type="button"
                                  className={stitchButton}
                                  disabled={!!busy}
                                  onClick={() =>
                                    running
                                      ? void control('reintentar', r.operacion)
                                      : void start(MONTHS.find((m) => r.periodo.toUpperCase().includes(m)) || period)
                                  }
                                >
                                  <RefreshCw size={14} />
                                  Reintentar
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {!rows.length && (
                    <Empty title={running ? 'Esperando la consulta del SAT…' : 'Sin filas'}>
                      La tabla se llena cuando el agente llega a «Consulta de declaraciones».
                    </Empty>
                  )}
                </div>
                {finished && job?.result?.analisis_id && (
                  <div className="actions">
                    <button type="button" className={stitchPrimary} onClick={() => onFinished(job.result.analisis_id!)}>
                      Ver la carpeta reanalizada
                    </button>
                  </div>
                )}
              </>
            )}
          </section>
        </div>

        <aside className="declara-step-side">
          <section className={stitchCard + ' padded declara-side-card'}>
            <h2>Inicio de sesión</h2>
            {status?.fiel.disponible ? (
              <p>
                <ShieldCheck size={15} aria-hidden="true" /> FIEL del gestor · {status.fiel.rfc}
                {status.fiel.vence && ` · vence ${longDate(status.fiel.vence.slice(0, 10))}`}
              </p>
            ) : (
              <p className="muted">La empresa no tiene una FIEL activa con .cer y .key en el gestor: usa CIEC.</p>
            )}
            <p className="muted">
              El .cer, el .key y la contraseña se entregan a Firefox en memoria: no salen de la bóveda a ningún archivo.
              {!status?.boveda_abierta && method === 'fiel' && ' Desbloquea el gestor antes de iniciar.'}
            </p>
            <p className="muted">Con CIEC, el captcha lo resuelves tú en la ventana de Firefox.</p>
            <ul className="declara-sat-checks">
              <li>Agente: {status?.agente.en_linea ? `en línea · ${status.agente.equipo || ''}` : 'sin conexión'}</li>
              <li>Portal SAT en el agente: {status?.portal ? 'habilitado' : 'no habilitado'}</li>
              <li>
                Firefox del agente: {browser == null ? 'consultando…' : browser.firefox ? 'instalado' : 'no instalado'}
                {browser && !browser.firefox && (
                  <button type="button" className={stitchButton} disabled={!!busy} onClick={install}>
                    {busy === 'instalar' ? 'Instalando…' : 'Instalar Firefox'}
                  </button>
                )}
              </li>
              <li>Ruta: {browser?.navegacion || 'Portal → Personas morales → «Pagos provisionales del ISR»'}</li>
            </ul>
          </section>
          <section className={stitchCard + ' padded declara-side-card'}>
            <h2>Protecciones</h2>
            <ul className="declara-sat-checks">
              {PROTECTIONS.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </section>
          <section className={stitchCard + ' padded declara-side-card'}>
            <h2>Destino</h2>
            <p className="declara-folder-path">{run.folder_path}</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
