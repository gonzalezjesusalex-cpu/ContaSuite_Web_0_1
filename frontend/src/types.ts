export interface CurrentUser {
  id: string;
  display_name: string;
  admin: boolean;
  role: 'admin' | 'contador' | 'auxiliar';
  bootstrap: boolean;
  company_ids: string[];
  write_company_ids: string[];
  /** Actions per visible company, decided by the server (catalog in backend/app/permissions.py). */
  actions?: Record<string, string[]>;
}
export interface Responsible {
  id: string;
  display_name: string;
  enabled: boolean;
}
export interface Company {
  archived?: boolean | null;
  archive_revision?: number;
  duplicate_rfc?: boolean;
  id: string;
  is_demo: boolean;
  name: string;
  rfc: string;
  person_type: 'Moral' | 'Física';
  trade_name: string;
  regime: string;
  accountant: string;
  /** Responsible accountant by user id (Bloque 2); null when unassigned. */
  accountant_id?: string | null;
  /** Original free text kept until an administrator retires it. */
  accountant_legacy?: string | null;
  // Bloque 1: data of the Constancia de Situación Fiscal (null when unknown).
  idcif?: string | null;
  curp?: string | null;
  tax_postal_code?: string | null;
  tax_street_type?: string | null;
  tax_street?: string | null;
  tax_exterior_number?: string | null;
  tax_interior_number?: string | null;
  tax_neighborhood?: string | null;
  tax_locality?: string | null;
  tax_municipality?: string | null;
  tax_state?: string | null;
  tax_between_streets?: string | null;
  operations_start?: string | null;
  padron_status?: string | null;
  csf_issued_on?: string | null;
  regimes?: { code: string | null; label: string; start_date: string | null; end_date: string | null }[];
  email: string;
  phone: string;
  location: string;
  folder: string;
  notes: string;
  created_at: string;
}
export interface Task {
  id: string;
  company_id: string;
  title: string;
  category: string;
  responsible: string;
  due_date: string;
  priority: string;
  status: string;
  notes: string;
}
export interface Obligation {
  id: string;
  company_id: string;
  title: string;
  period: string;
  due_date: string;
  status: string;
  reference: string;
  notes: string;
}
export interface Agent {
  id: string;
  online: boolean;
  capabilities: string[];
  last_seen: string;
}
/** One CFDI file placed in the virtual CFDI / month / emitidos-recibidos structure. */
export interface CfdiRow {
  p: string;
  g: 'xml' | 'pdf' | 'reporte';
  y: number | null;
  m: number | null;
  k: 'E' | 'R' | null;
  t: string;
  s: 'ok' | 'revisar';
  why: string;
  src: string;
}
/** A declaración or acuse, paired by period inside its folder; `pair` is the counterpart's path. */
export interface TaxRow {
  p: string;
  d: 'declaracion' | 'acuse' | 'otro';
  inf: boolean;
  a: 'federal' | 'estatal' | 'anual';
  y: number | null;
  n: number | null;
  q: string[];
  pair: string | null;
  s: 'ok' | 'faltante' | 'revisar';
  why: string;
}
/** An IMSS file placed in its monthly package; `fo` is the «Folio_…» folder when it is the SUA's copy. */
export interface ImssRow {
  p: string;
  c: string;
  y: number | null;
  m: number | null;
  fo: string;
  s: 'ok' | 'revisar';
  why: string;
}
export interface ImssMonth {
  y: number;
  m: number;
  have: string[];
  faltan: string[];
  sin_emision: string[];
  notas: string[];
  s: 'completo' | 'faltante' | 'parcial' | 'revisar';
}
/** The persistent virtual index of a company's folder (server side, cs_0014). */
export interface VirtualScanRow {
  id: string;
  created_at: string;
  finished_at: string | null;
  complete: boolean;
  total: number;
  added: number;
  changed: number;
  moved: number;
  restored: number;
  missing: number;
}
export interface VirtualIndexSummary {
  /** Files whose content is also stored inside ContaSuite (a copy goes stale when the original changes). */
  copia: { con_copia: number; bytes: number; pendientes: number };
  scans: VirtualScanRow[];
  latest: VirtualScanRow | null;
  sections: Record<string, number>;
  total: number;
  missing: number;
}
export interface VirtualFileRow {
  id: string;
  path: string;
  name: string;
  size: number;
  section: string;
  virtual_path: string;
  state: 'ok' | 'revisar';
  change: string;
  moved_from: string | null;
  first_seen: string;
  missing_since: string | null;
  copied: boolean;
}
/** One month and direction of the SAT report compared with the XML in the folder. */
export interface ReconPeriod {
  k: 'E' | 'R';
  y: number;
  m: number;
  xml: number;
  reporte: number | null;
  s: 'ok' | 'revisar' | 'sin_reporte_mes';
  ok: number;
  faltan: {
    u: string;
    tipo: string;
    fecha: string;
    total: number | null;
    emisor: string;
    receptor: string;
    cancelado: boolean;
  }[];
  n_faltan?: number;
  sobran: string[];
  n_sobran?: number;
  cancelados: number;
}
export interface PpdRow {
  u: string;
  p: string;
  k: 'E' | 'R' | null;
  y: number | null;
  m: number | null;
  tot: number | null;
  pagos: number;
  pagado: number;
  saldo: number | null;
  s: 'sin_pago' | 'parcial' | 'liquidada';
}
export interface CertRow {
  p: string;
  k: 'FIEL' | 'CSD' | 'RL' | '';
  desde: string;
  hasta: string;
  dias: number | null;
  s: 'vigente' | 'por_vencer' | 'vencido' | 'aun_no' | 'ilegible';
  rfcs: string[];
  emp: boolean;
  why: string;
}
export interface ExpedienteRow {
  p: string;
  t: string;
  o: string;
  s: 'ok' | 'revisar';
  why: string;
}
export interface FinanceRow {
  p: string;
  t: string;
  y: number | null;
  n: number | null;
  o: string;
}
export interface PayrollQuincena {
  y: number;
  q: number;
  label: string;
  xml: number;
  pdf: number;
  paired: number;
  sin_pdf: number;
  sin_xml: number;
  s: 'completo' | 'faltante';
  files: string[];
}
export interface WorkerRow {
  w: string;
  count: number;
  faltan: string[];
  files: { p: string; t: string }[];
}
export interface Job {
  id: string;
  company_id: string;
  agent_id: string;
  kind: string;
  status: string;
  result: {
    // Export (kind export_virtual): preview first (mode «preview»), then the copy (mode «apply»).
    // Internal copy (scan_folder with `copy`): what was stored inside ContaSuite.
    copia?: {
      archivos: number;
      subidos: number;
      ya_estaban: number;
      errores: number;
      sin_huella: number;
      marcados?: number;
      error?: string;
    };
    // SAT download (kind sat_declaraciones): where the browser is, and what it delivered at the end.
    progreso?: {
      fase: 'abriendo' | 'esperando_sesion' | 'descargando' | 'subiendo';
      total?: number;
      hechas?: number;
      guardadas?: number;
    };
    detectadas?: number;
    analisis_id?: string;
    guardadas?: number;
    entregados?: number;
    no_entregados?: number;
    fallidas?: {
      fila: number;
      motivo: string;
      operacion?: string;
      tipo?: string;
      periodo?: string;
      intentos?: number;
    }[];
    cancelar?: boolean;
    cancelada?: boolean;
    interrumpida?: string;
    mode?: 'preview' | 'apply';
    destination?: string;
    include?: string[];
    total?: number;
    bytes?: number;
    free_bytes?: number | null;
    enough_space?: boolean | null;
    collisions?: number;
    sections?: Record<string, { files: number; bytes: number; folders: number; sample: string[] }>;
    excluded?: Record<string, number>;
    omitted?: Record<string, number>;
    copiados?: number;
    duplicados?: number;
    errores?: number;
    omitidos?: number;
    manifiesto?: string;
    detalle_errores?: { p: string; motivo: string }[];
    files?: { name: string; relative_path: string; extension: string; size: number }[];
    summary?: {
      total: number;
      bytes: number;
      groups: {
        key: string;
        label: string;
        sensitive: boolean;
        count: number;
        bytes: number;
        extensions: Record<string, number>;
        subgroups: Record<string, number>;
        examples: string[];
      }[];
      extensions: Record<string, number>;
    };
    cfdi?: {
      rows: CfdiRow[];
      total: number;
      ok: number;
      revisar: number;
      dropped: number;
    };
    conciliacion?: {
      periodos: ReconPeriod[];
      con_reporte: number;
      ok: number;
      revisar: number;
      sin_reporte: number;
      faltan_xml: number;
      sin_reporte_xml: number;
    };
    ppd?: {
      rows: PpdRow[];
      total: number;
      sin_pago: number;
      parcial: number;
      liquidadas: number;
      pagos_ajenos: number;
      ajenos: { u: string; p: string }[];
    };
    certificados?: {
      rows: CertRow[];
      total: number;
      vigentes: number;
      por_vencer: number;
      vencidos: number;
      revisar: number;
    };
    expediente?: { rows: ExpedienteRow[]; total: number; faltan: string[]; revisar: number };
    finanzas?: { rows: FinanceRow[]; total: number; dropped: number };
    nomina?: {
      quincenas: PayrollQuincena[];
      huecos: number[];
      completas: number;
      faltantes: number;
      total: number;
    };
    trabajadores?: { workers: WorkerRow[]; total: number; personas: number; incompletos: number };
    imss?: {
      rows: ImssRow[];
      months: ImssMonth[];
      total: number;
      generales: number;
      completos: number;
      faltantes: number;
      revisar: number;
      registros: number;
    };
    impuestos?: {
      rows: TaxRow[];
      total: number;
      pairs: number;
      faltantes: number;
      revisar: number;
    };
    truncated?: boolean;
    error?: string;
    warnings?: string[];
  };
  created_at: string;
}
/** The signed-in user's local agent (Bloque 4). */
export interface AgentLinkStatus {
  state: 'online' | 'offline' | 'unlinked';
  roots: number;
  id?: string;
  agent_id?: string;
  machine?: string;
  user?: string | null;
  last_seen?: string | null;
}
export interface State {
  archive_available?: boolean;
  current_user: CurrentUser;
  companies: Company[];
  responsibles?: Responsible[];
  tasks: Task[];
  obligations: Obligation[];
  /** Visible documents per company (only companies the user may see). */
  document_counts: Record<string, number>;
  /** All documents visible to the user, including those not attributed to a company. */
  document_total: number;
  audit: { id: string; company_id: string; action: string; created_at: string }[];
  agents: Agent[];
  agent_link?: AgentLinkStatus | null;
  jobs: Job[];
  database: string;
  integrations: { sat: boolean; ocr: boolean; printing: boolean };
}

export interface StorageCompany {
  id: string;
  name: string;
  rfc: string;
}
export interface StorageSource {
  id: string;
  label: string;
  kind: string;
  enabled: boolean;
  state: string;
  code: string | null;
}
export interface StorageOptions {
  companies: StorageCompany[];
  sources: StorageSource[];
  max_file_bytes: number;
  upload_formats: string[];
  identity_mode: string;
  can_review: boolean;
  can_write: boolean;
  write_company_ids: string[];
  can_index: boolean;
  can_classify: boolean;
}
export interface StorageLocation {
  source_id: string;
  label: string;
  kind: string;
  availability: string;
  last_seen_at: string | null;
  error_code: string | null;
}
export interface StorageDocument {
  id: string;
  name: string;
  size: number;
  revision: number;
  company_ids: string[];
  companies: StorageCompany[];
  document_type: string;
  category: string;
  period: string | null;
  classification_status: string;
  created_at: string;
  format: string;
  sources: StorageLocation[];
  availability: string;
}
export interface StoragePage {
  items: StorageDocument[];
  total: number;
  pending_count: number;
  offset: number;
  limit: number;
}
export interface StorageVersion {
  number: number;
  original_name: string;
  sha256: string | null;
  size: number;
  media_type: string;
  created_at: string;
}
export interface StorageDetail {
  document: StorageDocument;
  versions: StorageVersion[];
}
