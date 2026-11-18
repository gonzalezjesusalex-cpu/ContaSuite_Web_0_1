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
      ' Crear el análisis con estos PDF se habilita en el siguiente paso.'
    );
  }
  return agentReady
    ? 'Descarga las declaraciones del SAT con el navegador de tu equipo.'
    : 'Este módulo analiza los PDF que cargues.';
}

export default function SatAccess({
  state,
  company,
  notify,
  refresh,
}: {
  state: State;
  company: string;
  notify: (m: string) => void;
  refresh: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
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
      await api('/jobs', 'POST', { company_id: company, kind: 'sat_declaraciones' });
      await refresh();
      notify('Descarga enviada a tu agente' + (link?.machine ? ' en ' + link.machine : '') + '.');
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="recopila-warning" role="status" aria-live="polite">
      <strong>Acceso SAT</strong>
      {capable ? (
        <>
          <p>{blocked && !active ? blocked : satMessage(job, true)}</p>
          <div className="actions">
            <button className={stitchButton} disabled={busy || active || !!blocked} onClick={start}>
              <Globe size={16} />
              {active ? 'Descargando…' : 'Descargar del SAT'}
            </button>
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
