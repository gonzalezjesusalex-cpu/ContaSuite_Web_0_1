import type { CertRow } from './types';

/** Mirror of `certificate_status` in backend/app/cert_groups.py (the single definition). The days are recomputed
 * from the certificate end date so a scan result that is weeks old still shows the current remaining days. */
export type CertState = 'vigente' | 'por_vencer' | 'critico' | 'vencido' | 'aun_no' | 'ilegible';

export function certState(row: Pick<CertRow, 'hasta_ts' | 'desde_ts' | 's' | 'dias'>, now = new Date()) {
  if (!row.hasta_ts) return { state: row.s as CertState, days: row.dias };
  const end = new Date(row.hasta_ts).getTime();
  const days = Math.floor((end - now.getTime()) / 86_400_000);
  let state: CertState = 'vigente';
  if (row.desde_ts && now.getTime() < new Date(row.desde_ts).getTime()) state = 'aun_no';
  else if (now.getTime() > end) state = 'vencido';
  else if (days < 30) state = 'critico';
  else if (days <= 90) state = 'por_vencer';
  return { state, days };
}

export const CERT_STATE_LABEL: Record<string, string> = {
  vigente: 'Vigente',
  por_vencer: 'Por vencer',
  critico: 'Crítico',
  vencido: 'Vencido',
  aun_no: 'Aún no vigente',
  ilegible: 'No se pudo leer',
};
export const CERT_KIND_LABEL: Record<string, string> = {
  FIEL: 'e.firma',
  CSD: 'CSD',
  RL: 'e.firma (representante)',
  '': 'Certificado',
};

/** The most urgent certificate of the company's own RFC that is expiring or expired (cambio 2.3). */
export function urgentCertificate(rows: CertRow[] | undefined, now = new Date()) {
  const mine = (rows || []).filter((r) => r.emp && r.hasta_ts && (r.k === 'FIEL' || r.k === 'CSD'));
  const latest = new Map<string, CertRow>();
  for (const r of mine) {
    const prev = latest.get(r.k);
    if (!prev || (r.hasta_ts || '') > (prev.hasta_ts || '')) latest.set(r.k, r);
  }
  return [...latest.values()]
    .map((row) => ({ row, ...certState(row, now) }))
    .filter((x) => ['por_vencer', 'critico', 'vencido'].includes(x.state))
    .sort((a, b) => (a.days ?? 0) - (b.days ?? 0))[0];
}
