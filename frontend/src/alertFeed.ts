import { useEffect, useState } from 'react';
import { api } from './api';
import type { AlertSeverity } from './alertTypes';

/** Una alerta de /integral/alert-feed (Configuración › Alertas y la campana). */
export type FeedAlert = {
  id: string;
  company_id: string;
  company_name: string;
  source: string;
  reference: string;
  kind: string;
  priority: AlertSeverity;
  generated_at: string | null;
  due_at: string | null;
  state: 'active' | 'snoozed' | 'resolved' | 'obsolete' | 'dismissed';
  revision: number | null;
  snooze_until: string | null;
  detail: string;
  changed_at: string | null;
  changed_by: string;
  reason: string;
};
export type Feed = {
  alerts: FeedAlert[];
  total: number;
  offset: number;
  limit: number;
  active_total: number;
  active_high: number;
  kinds: string[];
  lifecycle_available: boolean;
};
export type FeedQuery = {
  view?: 'active' | 'history';
  offset?: number;
  limit?: number;
  severity?: string;
  kind?: string;
  company_id?: string;
  q?: string;
};
export function feedPath(query: FeedQuery = {}) {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) if (value !== undefined && value !== '') q.set(key, String(value));
  const text = q.toString();
  return '/integral/alert-feed' + (text ? '?' + text : '');
}

/** Avisa a la campana y al menú de Configuración que una alerta cambió (posponer, descartar). */
export const ALERTS_CHANGED = 'contasuite-alerts-changed';
export const alertsChanged = () => window.dispatchEvent(new Event(ALERTS_CHANGED));

// Contador y las 5 más recientes: un solo pedido sirve a la campana y al menú de Configuración.
let shared: { at: number; promise: Promise<Feed> } | null = null;
function recent(force = false) {
  if (!force && shared && Date.now() - shared.at < 15000) return shared.promise;
  const promise = api<Feed>(feedPath({ limit: 5 }));
  shared = { at: Date.now(), promise };
  promise.catch(() => {
    if (shared?.promise === promise) shared = null;
  });
  return promise;
}

export function useRecentAlerts() {
  const [feed, setFeed] = useState<Feed | null>(null);
  useEffect(() => {
    let alive = true;
    const load = (force = false) =>
      recent(force)
        .then((f) => alive && setFeed(f))
        .catch(() => undefined); // sin alertas visibles si el servidor no responde; la página sigue
    load();
    const forced = () => load(true);
    const visible = () => document.visibilityState === 'visible' && load();
    const timer = window.setInterval(load, 60000);
    window.addEventListener(ALERTS_CHANGED, forced);
    window.addEventListener('contasuite-data-changed', forced);
    document.addEventListener('visibilitychange', visible);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener(ALERTS_CHANGED, forced);
      window.removeEventListener('contasuite-data-changed', forced);
      document.removeEventListener('visibilitychange', visible);
    };
  }, []);
  return feed;
}

/** «Nuevo»: las alertas que este usuario aún no ha visto al abrir la campana (se recuerda en el navegador). */
const seenKey = (userId: string) => 'contasuite-alerts-seen:' + userId;
export function seenAlerts(userId: string): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(seenKey(userId)) || '[]') as string[]);
  } catch {
    return new Set();
  }
}
export function markSeen(userId: string, ids: string[]) {
  const seen = seenAlerts(userId);
  ids.forEach((id) => seen.add(id));
  try {
    localStorage.setItem(seenKey(userId), JSON.stringify([...seen].slice(-500)));
  } catch {
    /* sin almacenamiento: el indicador «nuevo» vuelve a aparecer */
  }
}
