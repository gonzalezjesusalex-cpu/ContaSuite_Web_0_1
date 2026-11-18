import { useEffect, useState } from 'react';
import { Globe } from 'lucide-react';
import { api } from '../api';
import { stitchButton } from '../components/stitch';
import { can } from '../permissions';
import type { Job, State } from '../types';

const NOTE = 'Este módulo no solicita FIEL ni contraseñas: inicias sesión tú en la ventana del SAT.';

/** What the person should know or do now, in plain words, from the agent's state and the latest download. */
export function satMessage(job: Job | undefined, agentReady: boolean): string {
  if (job?.status === 'queued') return 'Esperando a que tu agente local abra el navegador…';
  if (job?.status === 'running') {
    const p = job.result.progreso;
    if (!p || p.fase === 'abriendo') return 'Abriendo el navegador en tu equipo…';
    if (p.fase === 'esperando_sesion')
      return 'Inicia sesión en el SAT en la ventana que se abrió y llega a «Consulta de declaraciones». Tú escribes tus datos allí; ContaSuite no los recibe.';
    if (p.fase === 'descargando')
      return `Descargando ${p.hechas ?? 0} de ${p.total ?? '…'} declaraciones · ${p.guardadas ?? 0} PDF guardados.`;
    return 'Enviando los PDF descargados a ContaSuite…';
  }
  if (job?.status === 'failed') return job.result.error || 'La descarga no se pudo completar.';
  if (job?.status === 'completed') {
    const r = job.result;
    const failed = r.fallidas?.length ?? 0;
    return (
      `Descarga terminada: ${r.entregados ?? 0} de ${r.detectadas ?? 0} PDF recibidos en ContaSuite` +
      (failed ? ` · ${failed} con error.` : '.') +
      (r.analisis_id ? ' El análisis ya está creado.' : r.entregados ? ' Ya puedes analizarlos.' : '')
    );
  }
  return agentReady
    ? 'Descarga las declaraciones del SAT con el navegador de tu equipo.'
    : 'Este módulo analiza los PDF que cargues.';
}

export default function SatAccess({
  state,
  company,
  shortName,
  onRun,
  notify,
  refresh,
}: {
  state: State;
  company: string;
  shortName: string;
  onRun: (runId: string) => void;
  notify: (m: string) => void;
  refresh: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState('');
  const link = state.agent_link;
  const agent = state.agents.find((a) => a.id === link?.agent_id);
  const capable = !!agent?.capabilities.includes('sat_declaraciones');
  const online = link?.state === 'online';
  const job = state.jobs.find((j) => j.kind === 'sat_declaraciones' && j.company_id === company);
  const active = job?.status === 'queued' || job?.status === 'running';
  // While the download runs, check every 3 s instead of waiting for the 60 s refresh.
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void refresh().catch(() => undefined), 3000);
    return () => clearInterval(timer);
  }, [active, refresh]);
  const allowed = !!company && can(state.current_user, 'declara.usar', company);
  const blocked = !company
    ? 'Elige una empresa para descargar sus declaraciones.'
    : link?.state === 'offline'
      ? 'Tu agente local está vinculado pero sin conexión' + (link.machine ? ' en ' + link.machine : '') + '.'
      : !online
        ? 'Tu agente local no está vinculado: abre ContaSuite en el equipo Windows donde se ejecuta el agente.'
        : !allowed
          ? 'Tu perfil no permite usar Declara en esta empresa.'
          : null;
  async function start() {
    setBusy(true);
    try {
      await api('/jobs', 'POST', {
        company_id: company,
        kind: 'sat_declaraciones',
        ...(year ? { ejercicio: Number(year) } : {}),
      });
      await refresh();
      notify('Descarga enviada a tu agente' + (link?.machine ? ' en ' + link.machine : '') + '.');
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function analyze() {
    if (!job) return;
    setBusy(true);
    try {
      const run = await api<{ id: string }>('/declara/runs/from-sat', 'POST', {
        job_id: job.id,
        short_name: shortName,
      });
      await refresh();
      onRun(run.id);
      notify('Análisis de Declara creado con los PDF descargados.');
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const delivered = job?.status === 'completed' && (job.result.entregados ?? 0) > 0;
  return (
    <div className="recopila-warning" role="status" aria-live="polite">
      <strong>Acceso SAT</strong>
      {capable ? (
        <>
          <p>{blocked && !active ? blocked : satMessage(job, true)}</p>
          <div className="actions">
            <label className="muted">
              Ejercicio{' '}
              <select value={year} disabled={active} onChange={(e) => setYear(e.target.value)}>
                <option value="">Todos los visibles</option>
                {[0, 1, 2, 3, 4].map((n) => (
                  <option key={n} value={String(thisYear - n)}>
                    {thisYear - n}
                  </option>
                ))}
              </select>
            </label>
            <button className={stitchButton} disabled={busy || active || !!blocked} onClick={start}>
              <Globe size={16} />
              {active ? 'Descargando…' : 'Descargar del SAT'}
            </button>
            {delivered && (
              <button
                className={stitchButton}
                disabled={busy || !shortName.trim()}
                onClick={job?.result.analisis_id ? () => onRun(job.result.analisis_id!) : analyze}
              >
                {job?.result.analisis_id ? 'Ver análisis' : 'Analizar PDF descargados'}
              </button>
            )}
          </div>
          <small className="muted">{NOTE}</small>
        </>
      ) : (
        <p>
          La descarga desde el SAT no está habilitada en el agente de este equipo. Este módulo analiza los PDF que
          cargues y no solicita FIEL ni contraseñas.
        </p>
      )}
    </div>
  );
}
