/** Diccionario único de alertas (Configuración › Alertas y la campana): el código interno nunca se muestra.
 *  Cada tipo tiene su frase en español, el texto de su acción directa y a dónde lleva esa acción. */
export type AlertSeverity = 'low' | 'medium' | 'high';
export type AlertRef = { kind: string; source: string; company_id: string; reference: string };
type Target = 'editar' | 'documentos' | 'obligaciones' | 'certificados' | 'expediente';
type AlertType = { text: string; action: string; target: Target };

export const SEVERITY: Record<AlertSeverity, { label: string; tone: 'neutral' | 'amber' | 'red' }> = {
  low: { label: 'Baja', tone: 'neutral' },
  medium: { label: 'Media', tone: 'amber' },
  high: { label: 'Alta', tone: 'red' },
};
export const severityOf = (priority: string) => SEVERITY[priority as AlertSeverity] || SEVERITY.low;

export const ALERT_TYPES: Record<string, AlertType> = {
  // Calidad de datos de la empresa y de sus documentos (dashboard integral).
  missing_responsible: { text: 'Sin responsable asignado', action: 'Asignar', target: 'editar' },
  missing_regime: { text: 'Sin régimen fiscal registrado', action: 'Completar', target: 'editar' },
  invalid_or_missing_rfc: { text: 'RFC inválido o faltante', action: 'Corregir', target: 'editar' },
  possible_duplicate_name: { text: 'Posible empresa duplicada por nombre', action: 'Revisar', target: 'editar' },
  document_pending_classification: { text: 'Documento sin clasificar', action: 'Clasificar', target: 'documentos' },
  document_without_company: { text: 'Documento sin empresa asociada', action: 'Asociar', target: 'documentos' },
  shared_document_review: {
    text: 'Documento asociado a varias empresas',
    action: 'Revisar',
    target: 'documentos',
  },
  certificate_dates_or_identity_mismatch: {
    text: 'Certificado con fechas o RFC que no coinciden',
    action: 'Revisar',
    target: 'certificados',
  },
  // Obligaciones del control fiscal.
  overdue: { text: 'Obligación vencida', action: 'Atender', target: 'obligaciones' },
  due_soon: { text: 'Obligación próxima a vencer', action: 'Atender', target: 'obligaciones' },
  unreviewed: { text: 'Obligación sin revisar', action: 'Revisar', target: 'obligaciones' },
  evidence_review: { text: 'Evidencia por revisar', action: 'Revisar', target: 'obligaciones' },
  documentation_review: { text: 'Documentación por revisar', action: 'Revisar', target: 'obligaciones' },
};
const UNKNOWN: AlertType = { text: 'Alerta del expediente', action: 'Abrir expediente', target: 'expediente' };

// Certificados: `<fiel|csd|unknown>_<estado>_<umbral en días>` (credential_alerts.candidates).
const CERT = /^(fiel|csd|unknown)_(expired|expiring|unknown|pending_verification)_(\d+)$/;
const CERT_NAME: Record<string, string> = { fiel: 'FIEL', csd: 'Sello digital (CSD)', unknown: 'Certificado' };

export function alertType(kind: string): AlertType {
  if (ALERT_TYPES[kind]) return ALERT_TYPES[kind];
  const cert = CERT.exec(kind);
  if (cert) {
    const [, which, state, days] = cert;
    const name = CERT_NAME[which];
    const female = which === 'fiel';
    const text =
      state === 'expired'
        ? `${name} ${female ? 'vencida' : 'vencido'}`
        : state === 'expiring'
          ? `${name} por vencer` + (Number(days) ? ` (${days} días o menos)` : '')
          : state === 'pending_verification'
            ? `${name} con vigencia aún no iniciada`
            : `${name} sin fechas de vigencia`;
    return {
      text,
      action: state === 'expired' || state === 'expiring' ? 'Renovar' : 'Revisar',
      target: 'certificados',
    };
  }
  return UNKNOWN;
}

export const alertText = (kind: string) => alertType(kind).text;

/** Ruta de la acción directa de cada tipo; «Abrir expediente» siempre lleva al expediente de la empresa. */
export function alertHref(alert: AlertRef, target: Target = alertType(alert.kind).target) {
  const base = '/empresas/' + encodeURIComponent(alert.company_id);
  if (target === 'editar') return base + '/editar';
  if (target === 'documentos') return base + '?tab=Documentos';
  if (target === 'obligaciones') return base + '?tab=Obligaciones';
  if (target === 'certificados') return base + '?tab=FIEL/CSD';
  return base;
}
export const dossierHref = (alert: AlertRef) => alertHref(alert, 'expediente');

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 31536000],
  ['month', 2592000],
  ['week', 604800],
  ['day', 86400],
  ['hour', 3600],
  ['minute', 60],
];
/** «hace 2 días»; la fecha exacta va en el `title`. */
export function relativeTime(iso: string | null | undefined, now = Date.now()) {
  if (!iso) return 'Sin fecha';
  const at = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z').getTime();
  if (Number.isNaN(at)) return 'Sin fecha';
  const seconds = Math.round((at - now) / 1000);
  const format = new Intl.RelativeTimeFormat('es-MX', { numeric: 'auto' });
  for (const [unit, size] of UNITS)
    if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit);
  return 'hace un momento';
}
export function exactTime(iso: string | null | undefined) {
  if (!iso) return '';
  const at = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z');
  return Number.isNaN(at.getTime()) ? '' : at.toLocaleString('es-MX', { dateStyle: 'long', timeStyle: 'short' });
}
