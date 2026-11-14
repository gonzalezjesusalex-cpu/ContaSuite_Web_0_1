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
export interface Job {
  id: string;
  company_id: string;
  agent_id: string;
  kind: string;
  status: string;
  result: {
    files?: { name: string; relative_path: string; extension: string; size: number }[];
    truncated?: boolean;
    error?: string;
    warnings?: string[];
  };
  created_at: string;
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
