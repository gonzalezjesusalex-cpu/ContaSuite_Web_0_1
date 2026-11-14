import { useEffect, useState } from 'react';
import { api } from '../api';

type Change = { before?: unknown; after?: unknown; changed?: boolean };
type Row = {
  id: string;
  action: string;
  created_at: string;
  actor: string;
  changes: Record<string, Change>;
};

const LABELS: Record<string, string> = {
  responsable: 'Contador responsable',
  acceso_anterior: 'Acceso del responsable anterior',
  accountant_legacy: 'Texto anterior de contador',
  archived: 'Archivada',
  name: 'Razón social',
  rfc: 'RFC',
  person_type: 'Tipo de persona',
  trade_name: 'Nombre comercial',
  regime: 'Régimen fiscal',
  accountant: 'Contador (texto)',
  email: 'Correo',
  phone: 'Teléfono',
  location: 'Ubicación',
  folder: 'Ruta de carpeta',
  notes: 'Observaciones',
  title: 'Título',
  category: 'Categoría',
  responsible: 'Responsable de la tarea',
  due_date: 'Fecha límite',
  priority: 'Prioridad',
  status: 'Estado',
  period: 'Periodo',
  reference: 'Referencia',
};

const ACCESS: Record<string, string> = {
  keep: 'se conserva',
  read: 'queda en lectura',
  remove: 'se retira',
};

function shown(value: unknown, key: string): string {
  if (value === null || value === undefined || value === '') return 'vacío';
  if (typeof value === 'boolean') return value ? 'sí' : 'no';
  if (key === 'acceso_anterior' && typeof value === 'string') return ACCESS[value] || value;
  if (typeof value === 'object') {
    const person = value as { display_name?: string; name?: string; enabled?: boolean };
    const name = person.display_name || person.name;
    if (name) return name + (person.enabled === false ? ' (inactivo)' : '');
    return 'vacío';
  }
  return String(value);
}

function describe(key: string, change: Change): string {
  const label = LABELS[key] || key;
  if (change.changed) return label + ': modificada';
  if (!('before' in change)) return label + ': ' + shown(change.after, key);
  return label + ': ' + shown(change.before, key) + ' → ' + shown(change.after, key);
}

/** Change history of one company: who, when, what, and previous and new values (Bloque 2). */
export default function CompanyHistory({ companyId }: { companyId: string }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    setRows(null);
    setError('');
    const abort = new AbortController();
    api<Row[]>('/companies/' + companyId + '/history', 'GET', undefined, abort.signal)
      .then(setRows)
      .catch((e) => {
        if (!abort.signal.aborted) setError((e as Error).message);
      });
    return () => abort.abort();
  }, [companyId]);
  return (
    <div className="card">
      <div className="card-title">
        <div>
          <h2>Historial</h2>
          <p>Quién hizo cada cambio, cuándo y qué valores tenía antes. Los registros anteriores no tienen autor.</p>
        </div>
      </div>
      {error ? (
        <p className="error-banner" role="alert">
          {error}
        </p>
      ) : rows === null ? (
        <p role="status">Consultando historial…</p>
      ) : rows.length === 0 ? (
        <p className="muted padded">Sin cambios registrados.</p>
      ) : (
        <div className="audit-list">
          {rows.map((r) => (
            <div key={r.id}>
              <span className="timeline-dot" />
              <div>
                <strong>{r.action}</strong>
                <small>
                  {r.actor} · {new Date(r.created_at).toLocaleString('es-MX')}
                </small>
                {Object.entries(r.changes).map(([key, change]) => (
                  <small key={key}>{describe(key, change)}</small>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
