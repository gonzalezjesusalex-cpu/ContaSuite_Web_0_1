import { useEffect, useState } from 'react';
import { api } from '../api';
import { stitchButton, stitchCard, stitchPrimary } from '../components/stitch';

type Row = {
  company_id: string;
  company: string;
  legacy_text: string;
  accountant_id: string | null;
  status: 'assigned' | 'match' | 'ambiguous' | 'none';
  candidates: { id: string; display_name: string }[];
};

const STATUS = {
  assigned: 'Ya asignada',
  match: 'Coincidencia exacta',
  ambiguous: 'Varias coincidencias',
  none: 'Sin coincidencia',
};

/**
 * Old free-text accountants against accounts, by exact name (Bloque 2). Nothing is applied until the
 * administrator confirms each row; the original text is kept until its retirement is confirmed too.
 */
export default function ResponsibleReconciliation({ notify }: { notify: (m: string) => void }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const c = new AbortController();
    api<Row[]>('/responsible/reconciliation', 'GET', undefined, c.signal)
      .then((data) => {
        setRows(data);
        // A unique exact match is pre-selected but still needs the explicit confirmation below.
        setChosen(
          Object.fromEntries(data.filter((r) => r.status === 'match').map((r) => [r.company_id, r.candidates[0].id])),
        );
      })
      .catch((e) => {
        if (!c.signal.aborted) setError((e as Error).message);
      });
    return () => c.abort();
  }, [reload]);
  async function run(path: string, body: unknown, message: string) {
    setBusy(true);
    setError('');
    try {
      await api('/responsible/reconciliation/' + path, 'POST', body);
      notify(message);
      setReload((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const pending = (rows || []).filter((r) => !r.accountant_id && chosen[r.company_id]);
  const retirable = (rows || []).filter((r) => r.accountant_id);
  if (rows && !rows.length) return null;
  return (
    <section className={stitchCard + ' padded'}>
      <div className="documents-header">
        <h2>Conciliación de contadores</h2>
      </div>
      <p className="muted">
        El contador de las empresas era texto libre. Revisa la coincidencia por nombre exacto con las cuentas de
        contador; nada se asigna hasta que lo confirmes. El texto original se conserva hasta que confirmes su retiro.
      </p>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      {!rows ? (
        <p role="status">Consultando…</p>
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Empresa</th>
                  <th>Texto anterior</th>
                  <th>Estado</th>
                  <th>Contador propuesto</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.company_id}>
                    <td>{r.company}</td>
                    <td>{r.legacy_text}</td>
                    <td>{STATUS[r.status]}</td>
                    <td>
                      {r.accountant_id ? (
                        'Asignada'
                      ) : r.candidates.length ? (
                        <select
                          aria-label={'Contador para ' + r.company}
                          disabled={busy}
                          value={chosen[r.company_id] || ''}
                          onChange={(e) => setChosen((old) => ({ ...old, [r.company_id]: e.target.value }))}
                        >
                          <option value="">No asignar</option>
                          {r.candidates.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.display_name}
                            </option>
                          ))}
                        </select>
                      ) : (
                        'Revisión manual desde el expediente'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="actions">
            <button
              className={stitchPrimary}
              disabled={busy || !pending.length}
              onClick={() =>
                window.confirm('¿Asignar ' + pending.length + ' empresa(s) a los contadores seleccionados?') &&
                void run(
                  'apply',
                  { items: pending.map((r) => ({ company_id: r.company_id, accountant_id: chosen[r.company_id] })) },
                  'Responsables asignados.',
                )
              }
            >
              Confirmar {pending.length} asignaciones
            </button>
            <button
              className={stitchButton}
              disabled={busy || !retirable.length}
              onClick={() =>
                window.confirm('¿Retirar el texto anterior de ' + retirable.length + ' empresa(s) ya asignadas?') &&
                void run('retire', { company_ids: retirable.map((r) => r.company_id) }, 'Texto anterior retirado.')
              }
            >
              Retirar texto anterior ({retirable.length})
            </button>
          </div>
        </>
      )}
    </section>
  );
}
