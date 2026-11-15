import { api } from './api';
import type { AgentLinkStatus } from './types';

// Bloque 4, option A: the browser hands a one-time code to the agent running on this computer. The agent only
// answers pages of this app (CORS in agent/agent.py) and keeps its credential in memory.
export const AGENT_LOCAL_URL = 'http://127.0.0.1:47865';

type LocalStatus = { agent_id: string; paired: boolean; user: string | null; notice: string };

async function local<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 2500);
  try {
    const response = await fetch(AGENT_LOCAL_URL + path, { ...init, signal: controller.signal, credentials: 'omit' });
    if (!response.ok) throw new Error('agent ' + response.status);
    return (await response.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Pairs the local agent with the signed-in user when it is not already paired to them.
 * Returns what happened, never throws: no agent on this computer is a normal situation.
 */
export async function pairLocalAgent(
  status: AgentLinkStatus | null | undefined,
  displayName: string,
): Promise<'paired' | 'already' | 'absent' | 'failed'> {
  let current: LocalStatus;
  try {
    current = await local<LocalStatus>('/status');
  } catch {
    return 'absent';
  }
  // Already working for this user through a live link: nothing to do.
  if (current.paired && current.user === displayName && status?.state !== 'unlinked') return 'already';
  try {
    const { code } = await api<{ code: string }>('/agent-links/code', 'POST');
    await local('/pair', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    return 'paired';
  } catch {
    return 'failed';
  }
}

/** Header text: «Agente conectado como Ana» or why it is not connected. */
export function agentLabel(status: AgentLinkStatus | null | undefined, local: string): string {
  if (status?.state === 'online') return 'Agente conectado como ' + (status.user || 'tu usuario');
  if (status?.state === 'offline')
    return 'Agente vinculado sin conexión' + (status.machine ? ' (' + status.machine + ')' : '');
  if (local === 'absent') return 'Agente no detectado en este equipo';
  if (local === 'failed') return 'No se pudo vincular el agente';
  return 'Agente sin vincular';
}
