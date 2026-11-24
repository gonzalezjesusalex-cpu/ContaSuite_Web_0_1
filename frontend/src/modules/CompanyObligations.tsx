import { useEffect, useState } from 'react';
import { api } from '../api';
import { Badge } from '../components/ui';
import { stitchButton, stitchCard } from '../components/stitch';
import './v11.css';

type Assignment = {
  obligation_id: string;
  short_name: string;
  official_name: string;
  group: string;
  cadence: string;
  due_text: string | null;
  applicable: boolean;
  revision: number;
  start_date: string | null;
  end_date: string | null;
  source: string | null;
};
const CADENCE: Record<string, string> = {
  monthly: 'Mensual',
  bimonthly: 'Bimestral',
  quarterly: 'Trimestral',
  annual: 'Anual',
};

/** Plan v1.1, Cambio 2: which CSF obligations apply to the company and between which dates (confirm or correct). */
export default function CompanyObligations({ companyId, notify }: { companyId: string; notify: (s: string) => void }) {
  const [items, setItems] = useState<Assignment[] | null>(null);
  const [canEdit, setCanEdit] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, Partial<Assignment>>>({});
  const [showAll, setShowAll] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    api<{ items: Assignment[]; can_edit: boolean }>(`/fiscal-control/companies/${companyId}/assignments`)
      .then((d) => {
        setItems(d.items);
        setCanEdit(d.can_edit);
        setDrafts({});
      })
      .catch((e) => setError(e.message));
  }, [companyId, reload]);
  async function save(a: Assignment) {
    const d = { ...a, ...drafts[a.obligation_id] };
    try {
      await api('/fiscal-control/applicability', 'PUT', {
        company_id: companyId,
        obligation_id: a.obligation_id,
        applicable: d.applicable,
        revision: a.revision,
        start_date: d.start_date || null,
        end_date: d.end_date || null,
        source: a.source === 'csf' && d.start_date === a.start_date && d.end_date === a.end_date ? 'csf' : 'manual',
      });
      notify('Obligación actualizada');
      setReload((n) => n + 1);
    } catch (e) {
      notify((e as Error).message);
    }
  }
  const shown = (items || []).filter((a) => showAll || a.applicable || drafts[a.obligation_id]?.applicable);
  return (
    <section className={stitchCard + ' padded v11-assignments'}>
      <div className="card-title">
        <div>
          <h2>Obligaciones de la constancia</h2>
          <p>
            Se proponen desde la Constancia de Situación Fiscal con sus fechas de inicio y fin; aquí se confirman o
            corrigen. Sólo aparecen en el periodo cuando están dentro de esas fechas.
          </p>
        </div>
        <label className="check-option">
          <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> Ver todo el
          catálogo
        </label>
      </div>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {items && !shown.length && (
        <p className="muted">
          La empresa no tiene obligaciones de constancia asignadas. Actualízala con su CSF o marca «Ver todo el
          catálogo» para asignarlas a mano.
        </p>
      )}
      {shown.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Aplica</th>
                <th scope="col">Obligación</th>
                <th scope="col">Periodicidad</th>
                <th scope="col">Inicio</th>
                <th scope="col">Fin</th>
                <th scope="col">Origen</th>
                {canEdit && <th scope="col">Acción</th>}
              </tr>
            </thead>
            <tbody>
              {shown.map((a) => {
                const d = { ...a, ...drafts[a.obligation_id] };
                const set = (patch: Partial<Assignment>) =>
                  setDrafts((old) => ({ ...old, [a.obligation_id]: { ...old[a.obligation_id], ...patch } }));
                const changed = !!drafts[a.obligation_id];
                return (
                  <tr key={a.obligation_id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={'Aplica: ' + a.official_name}
                        disabled={!canEdit}
                        checked={!!d.applicable}
                        onChange={(e) => set({ applicable: e.target.checked })}
                      />
                    </td>
                    <td>
                      {a.official_name}
                      <small className="muted">
                        {' '}
                        · {a.group}
                        {a.due_text && ' · ' + a.due_text}
                      </small>
                    </td>
                    <td>{CADENCE[a.cadence] || a.cadence}</td>
                    <td>
                      <input
                        type="date"
                        aria-label="Fecha de inicio"
                        disabled={!canEdit}
                        value={d.start_date || ''}
                        onChange={(e) => set({ start_date: e.target.value || null })}
                      />
                    </td>
                    <td>
                      <input
                        type="date"
                        aria-label="Fecha de fin"
                        disabled={!canEdit}
                        value={d.end_date || ''}
                        onChange={(e) => set({ end_date: e.target.value || null })}
                      />
                    </td>
                    <td>
                      {a.source === 'csf' ? (
                        <Badge tone="blue">Leída de la CSF</Badge>
                      ) : a.source ? (
                        <Badge>Capturada a mano</Badge>
                      ) : (
                        '—'
                      )}
                    </td>
                    {canEdit && (
                      <td>
                        <button className={stitchButton} disabled={!changed} onClick={() => save(a)}>
                          Guardar
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
