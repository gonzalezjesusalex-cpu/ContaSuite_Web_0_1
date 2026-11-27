// Declara (rediseño del 26/11/2026): tipos del API y textos compartidos por los pasos.

export type MonthState = 'COMPLETO' | 'POR_VENCER' | 'VENCIDO' | 'EN_CURSO' | 'FUTURO' | 'NO_APLICA_ALTA';

export type Month = {
  numero: number;
  estado: MonthState;
  declaracion: boolean;
  acuse: boolean;
  falta: string[];
  complementarias: number;
  resico: number;
  salarios: number;
  vence: string;
  exigible: boolean;
};

export type Summary = {
  total?: number;
  rename?: number;
  correct?: number;
  identical?: number;
  omitted?: number;
  rfc_other?: number;
  excluded_manual?: number;
  manual?: number;
  excluded?: number;
  special?: number;
  other_year?: number;
  renamed?: number;
  output?: number;
  primary_rfc?: string | null;
  rfc_matches?: boolean;
  year?: number;
  due_day?: number;
  alta?: { fecha: string | null; origen: 'Constancia' | 'RFC' | null };
};

export type Run = {
  id: string;
  company_id: string;
  short_name: string;
  expected_rfc: string;
  name: string;
  status: string;
  revision: number;
  message: string;
  created_at: string;
  evaluated_on: string;
  year: number | null;
  mode: string | null;
  folder_path: string | null;
  months: Record<string, Record<string, Month>>;
  summary: Summary;
  warnings: string[];
};

export type PdfRecord = {
  index: number;
  path: string;
  expected_name: string | null;
  status: string;
  detail: string;
  rfc: string | null;
  razon_social: string | null;
  year: string | null;
  month: string | null;
  operation: string | null;
  document_kind: string | null;
  declaration_type: string | null;
  complement_type: string | null;
  is_resico: boolean;
  is_salarios: boolean;
  manual_override: boolean;
  identical_to: string | null;
  count_in_control: boolean;
  origin: string;
  sha256: string;
  other_year: boolean;
  can_undo: boolean;
};

export type Detail = { run: Run; records: PdfRecord[] };

export type Preview = {
  name: string | null;
  errors: string[];
  warnings: string[];
  standard: { choice: string; month: string; texto: string; document_kind: string; declaration_type: string } | null;
  effect: { month: string; before: MonthState; after: MonthState } | null;
};

export type CompanyView = {
  company_id: string;
  rfc: string;
  name: string;
  person_type: string;
  short_name: string;
  short_name_saved: boolean;
  suggested: string;
  mode: string;
  alta: { fecha: string | null; origen: 'Constancia' | 'RFC' | null };
};

export type LogEntry = {
  id: string;
  created_at: string;
  action: string;
  label: string;
  user: string;
  machine: string;
  year: number | null;
  run_id: string | null;
  detail: Record<string, unknown>;
  path: string;
};

export const RUN_LABELS: Record<string, string> = {
  analyzing: 'Analizando',
  analyzed: 'Listo para revisar',
  editing: 'Guardando revisión',
  generating: 'Generando copias',
  generated: 'Terminado',
  error: 'Revisar error',
};

export const STATUS_LABELS: Record<string, string> = {
  RENOMBRAR: 'Por renombrar',
  CORRECTO: 'Correcto',
  OMITIDO: 'Omitido',
  ERROR: 'Error',
  'RFC DIFERENTE': 'RFC diferente',
  'COPIA IDÉNTICA': 'Copia idéntica',
  EXCLUIDO: 'Excluido',
};

export const STATUS_TONES: Record<string, string> = {
  RENOMBRAR: 'blue',
  CORRECTO: 'green',
  OMITIDO: 'amber',
  ERROR: 'red',
  'RFC DIFERENTE': 'red',
  'COPIA IDÉNTICA': 'neutral',
  EXCLUIDO: 'neutral',
};

export const MONTH_STATES: Record<MonthState, { label: string; tone: string }> = {
  COMPLETO: { label: 'Completo', tone: 'green' },
  POR_VENCER: { label: 'Por vencer', tone: 'amber' },
  VENCIDO: { label: 'Vencido o incompleto', tone: 'red' },
  EN_CURSO: { label: 'En curso', tone: 'neutral' },
  FUTURO: { label: 'Futuro', tone: 'neutral' },
  NO_APLICA_ALTA: { label: 'No aplica por fecha de alta', tone: 'neutral' },
};

export const MONTHS = [
  'ENERO',
  'FEBRERO',
  'MARZO',
  'ABRIL',
  'MAYO',
  'JUNIO',
  'JULIO',
  'AGOSTO',
  'SEPTIEMBRE',
  'OCTUBRE',
  'NOVIEMBRE',
  'DICIEMBRE',
];

const SHORT = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

export const monthLabel = (month: string) => month.charAt(0) + month.slice(1).toLowerCase();

/** «17 nov» from an ISO date, without time zone surprises. */
export function shortDate(iso: string) {
  const [, m, d] = iso.split('-').map(Number);
  return `${d} ${SHORT[m - 1]}`;
}

export function longDate(iso: string | null) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

/** Same cleanup as the engine's `sanitize_company_name`. */
export function sanitizeShortName(value: string) {
  return value
    .trim()
    .replace(/[<>:"/\\|?*]+/g, ' ')
    .replace(/\s+/g, ' ')
    .toUpperCase()
    .replace(/^[ .]+|[ .]+$/g, '');
}

export const FORBIDDEN = /[<>:"/\\|?*]/;

export const fileName = (path: string) => path.split('/').pop() || path;

export const documentLabel = (r: Pick<PdfRecord, 'document_kind' | 'declaration_type'>) =>
  r.document_kind
    ? (r.document_kind === 'ACUSE' ? 'Acuse' : 'Declaración') +
      (r.declaration_type ? ' ' + r.declaration_type.toLowerCase() : '')
    : 'Sin identificar';

export type Filter = { id: string; label: string; test: (r: PdfRecord) => boolean };

export const FILTERS: Filter[] = [
  { id: 'todos', label: 'Todos', test: () => true },
  { id: 'renombrar', label: 'Por renombrar', test: (r) => r.status === 'RENOMBRAR' },
  { id: 'correctos', label: 'Correctos', test: (r) => r.status === 'CORRECTO' },
  { id: 'resico', label: 'RESICO', test: (r) => r.is_resico },
  { id: 'salarios', label: 'SALARIOS', test: (r) => r.is_salarios },
  { id: 'copias', label: 'Copias idénticas', test: (r) => r.status === 'COPIA IDÉNTICA' },
  { id: 'omitidos', label: 'Omitidos/error', test: (r) => ['OMITIDO', 'ERROR', 'RFC DIFERENTE'].includes(r.status) },
  { id: 'excluidos', label: 'Excluidos', test: (r) => r.status === 'EXCLUIDO' },
];
