import { useEffect, useState, type FormEvent } from 'react';
import { api } from '../api';
import { Field, Modal } from '../components/ui';
import { stitchButton, stitchPrimary } from '../components/stitch';
import type { Company, Responsible } from '../types';

type Candidate = { id: string; display_name: string; username: string };
export type PreviousAccess = 'keep' | 'read' | 'remove';

/** Active accountants an administrator can assign (Bloque 2). Disabled accounts are never offered. */
export function useCandidates() {
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const abort = new AbortController();
    api<Candidate[]>('/responsible/candidates', 'GET', undefined, abort.signal)
      .then(setCandidates)
      .catch((e) => {
        if (!abort.signal.aborted) setError((e as Error).message);
      });
    return () => abort.abort();
  }, []);
  return { candidates, error };
}

/** Searchable selector of the responsible accountant: «Ana Pérez · ana» or «Sin asignar». */
export function ResponsibleSelect({
  value,
  current,
  onChange,
  disabled,
}: {
  value: string;
  /** The company's current responsible, shown even if disabled until it is reassigned. */
  current?: Responsible | null;
  onChange: (id: string) => void;
  disabled?: boolean;
}) {
  const { candidates, error } = useCandidates();
  const [search, setSearch] = useState('');
  const term = search.trim().toLocaleLowerCase('es');
  const shown = (candidates || []).filter(
    (c) =>
      c.id === value ||
      !term ||
      c.display_name.toLocaleLowerCase('es').includes(term) ||
      c.username.toLocaleLowerCase('es').includes(term),
  );
  const inactive = current && !current.enabled && !shown.some((c) => c.id === current.id) ? current : null;
  return (
    <div className="responsible-select">
      <input
        type="search"
        aria-label="Buscar contador"
        placeholder="Buscar contador por nombre o usuario"
        value={search}
        disabled={disabled}
        onChange={(e) => setSearch(e.target.value)}
      />
      <select
        aria-label="Contador responsable"
        value={value}
        disabled={disabled || candidates === null}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Sin asignar</option>
        {inactive && <option value={inactive.id}>{inactive.display_name} (inactivo)</option>}
        {shown.map((c) => (
          <option key={c.id} value={c.id}>
            {c.display_name} · {c.username}
          </option>
        ))}
      </select>
      {candidates === null && !error && <small role="status">Consultando contadores…</small>}
      {error && <small role="alert">{error}</small>}
      {candidates?.length === 0 && <small>No hay contadores activos. Créalos en Configuración › Cuentas.</small>}
    </div>
  );
}

/** What happens to the previous responsible's access; asked whenever it is replaced or removed. */
export function PreviousAccessField({
  value,
  onChange,
  disabled,
}: {
  value: PreviousAccess | '';
  onChange: (v: PreviousAccess) => void;
  disabled?: boolean;
}) {
  return (
    <Field label="Acceso del responsable anterior *">
      <select
        required
        aria-label="Acceso del responsable anterior"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value as PreviousAccess)}
      >
        <option value="" disabled>
          Elige qué hacer
        </option>
        <option value="keep">Conservar su acceso</option>
        <option value="read">Dejarle sólo lectura</option>
        <option value="remove">Retirarle el acceso</option>
      </select>
    </Field>
  );
}

/** Calls the server; returns its notices (for example, the write access granted to the new responsible). */
export async function saveResponsible(company: Company, accountantId: string, previous: PreviousAccess | '') {
  const result = await api<{ notices: string[] }>('/responsible/companies/' + company.id, 'PUT', {
    current_accountant_id: company.accountant_id || null,
    accountant_id: accountantId || null,
    ...(company.accountant_id ? { previous_access: previous || null } : {}),
  });
  return result.notices;
}

/** Dialog of the dossier to assign, change or remove the responsible accountant (administrators only). */
export function ResponsibleDialog({
  company,
  current,
  onClose,
  onSaved,
}: {
  company: Company;
  current?: Responsible | null;
  onClose: () => void;
  onSaved: (notices: string[]) => void;
}) {
  const [value, setValue] = useState(company.accountant_id || '');
  const [previous, setPrevious] = useState<PreviousAccess | ''>('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const changing = value !== (company.accountant_id || '');
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!changing) return onClose();
    setBusy(true);
    setError('');
    try {
      onSaved(await saveResponsible(company, value, previous));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Contador responsable" onClose={() => !busy && onClose()}>
      <form className="padded" onSubmit={submit}>
        <p className="muted">
          Sólo un contador activo puede ser responsable. Al asignarlo se le concede acceso de escritura a la empresa.
        </p>
        <div className="form-grid">
          <Field label="Contador responsable" wide>
            <ResponsibleSelect value={value} current={current} onChange={setValue} disabled={busy} />
          </Field>
          {changing && company.accountant_id && (
            <PreviousAccessField value={previous} onChange={setPrevious} disabled={busy} />
          )}
        </div>
        {error && (
          <p className="error-banner" role="alert">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="button" className={stitchButton} disabled={busy} onClick={onClose}>
            Cancelar
          </button>
          <button className={stitchPrimary} disabled={busy || !changing}>
            Guardar responsable
          </button>
        </div>
      </form>
    </Modal>
  );
}
