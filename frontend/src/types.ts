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
export interface Job {
  id: string;
  company_id: string;
  agent_id: string;
  kind: string;
  status: string;
  result: {
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
