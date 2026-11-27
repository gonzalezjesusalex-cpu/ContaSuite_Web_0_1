// Declara en modo carpeta: los trabajos los hace el agente del equipo; la web los encola y espera su resultado.
import { api } from '../../api';

export type FolderJob<T> = {
  id: string;
  op: string;
  status: string;
  result: T & { error?: string; error_code?: string };
};

export type Lock = { estado: 'libre' | 'propio' | 'ajeno'; usuario?: string; equipo?: string; desde?: string };

export type Probe = { ruta: string; lectura: boolean; escritura: boolean; latencia_ms: number | null; bloqueo: Lock };

export type Listing = {
  ruta: string;
  padre: string | null;
  pdf: number;
  bloqueo: Lock;
  carpetas: {
    nombre: string;
    ruta: string;
    pdf: number;
    legible: boolean;
    indice: boolean;
    plantilla: boolean;
    bloqueo: Lock;
  }[];
};

export type CompanyFolder = {
  vinculada: { ruta: string; origen: string } | null;
  plantilla: string;
  ruta: string;
  origen: string | null;
  recientes: string[];
  raices: string[];
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Espera el resultado de un trabajo del agente. Lanza el error que el agente informó, en español. */
export async function waitJob<T>(jobId: string, timeoutMs = 120_000): Promise<T> {
  const started = Date.now();
  let delay = 500;
  while (Date.now() - started < timeoutMs) {
    const job = await api<FolderJob<T>>('/declara/folder/jobs/' + jobId);
    if (job.status === 'completed') return job.result;
    if (job.status === 'failed') throw new Error(job.result.error || 'El agente no pudo completar la operación.');
    await sleep(delay);
    delay = Math.min(delay + 250, 1500);
  }
  throw new Error('El agente no respondió a tiempo. Revisa que esté en ejecución en este equipo.');
}

export async function folderOp<T>(companyId: string, op: string, ruta = '', plantilla = ''): Promise<T> {
  const { job_id } = await api<{ job_id: string }>('/declara/folder', 'POST', {
    company_id: companyId,
    op,
    ruta,
    plantilla,
  });
  return waitJob<T>(job_id, 60_000);
}

export const lockText = (lock?: Lock | null) =>
  !lock || lock.estado === 'libre'
    ? 'Libre'
    : lock.estado === 'propio'
      ? `Bloqueada por ti${lock.equipo ? ' · ' + lock.equipo : ''}`
      : `En uso por ${lock.usuario || 'otra persona'}${lock.equipo ? ' · ' + lock.equipo : ''}${
          lock.desde ? ' desde ' + new Date(lock.desde).toLocaleTimeString('es-MX', { timeStyle: 'short' }) : ''
        } · solo lectura`;
