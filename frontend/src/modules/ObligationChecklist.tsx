import { useEffect, useState } from 'react';
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Download,
  LayoutGrid,
  MinusCircle,
  Table2,
  X,
} from 'lucide-react';
import { api, downloadApi } from '../api';
import { stitchButton, stitchPrimary } from '../components/stitch';
import DocumentLights, { type CompanyLights } from './DocumentLights';
import ObligationCatalog from './ObligationCatalog';
import './v11.css';

/** Plan v1.1, Cambio 2: obligations of each company in the period, each with a «done» box. */
export type ChecklistItem = {
  obligation_id: string;
  short_name: string;
  official_name: string;
  group: string;
  cadence: string;
  period_id: string;
  done: boolean;
  not_applicable: boolean;
  revision: number;
  due_date: string | null;
  due_text: string | null;
  overdue: boolean;
  marked_by: string | null;
  marked_at: string | null;
};
type Totals = { done: number; total: number; pending: number; overdue: number };
type CompanyRow = Totals & {
  id: string;
  name: string;
  rfc: string;
  person_type: string;
  accountant: string;
  accountant_id: string | null;
  items: ChecklistItem[];
};
type Checklist = {
  year: number;
  month: number;
  groups: string[];
  catalog: { id: string; short_name: string; official_name: string; group: string; cadence: string }[];
  companies: CompanyRow[];
  summary: Totals;
};

const date = (iso: string | null) => (iso ? new Date(iso + 'T12:00:00').toLocaleDateString('es-MX') : '');

function Box({
  item,
  company,
  busy,
  onToggle,
}: {
  item: ChecklistItem;
  company: CompanyRow;
  busy: boolean;
  onToggle: (c: CompanyRow, i: ChecklistItem) => void;
}) {
  const state = item.done ? 'Hecha' : item.overdue ? 'Vencida' : 'Pendiente';
  const who =
    item.marked_by && item.marked_at
      ? ` · marcó ${item.marked_by} el ${new Date(item.marked_at).toLocaleString('es-MX')}`
      : '';
  return (
    <label
      className={'v11-check ' + (item.done ? 'is-done' : item.overdue ? 'is-overdue' : '')}
      title={item.official_name + who}
    >
      <input type="checkbox" checked={item.done} disabled={busy} onChange={() => onToggle(company, item)} />
      <span>
        <span className="v11-check-name">{item.short_name}</span>
        <small>
          {state}
          {item.due_date && ' · vence ' + date(item.due_date)}
        </small>
      </span>
    </label>
  );
}

const CADENCE: Record<string, string> = {
  monthly: 'Mensual',
  bimonthly: 'Bimestral',
  quarterly: 'Trimestral',
  annual: 'Anual',
};
function groupBar(items: ChecklistItem[]) {
  const done = items.filter((i) => i.done).length;
  const tone = items.some((i) => i.overdue) ? ' is-overdue' : done === items.length ? ' is-done' : '';
  return { done, tone };
}
const typeName = (t: string) => (t === 'Física' ? 'Persona física' : t === 'Moral' ? 'Persona moral' : t || '—');

/** Rediseño v2: one company card (Obligaciones › Matriz del mes, vista tarjetas): type, RFC, responsible,
 *  document traffic light and the obligations grouped by tax family, each group with its bar and boxes. */
function CompanyCard({
  company: c,
  lights,
  groups,
  busy,
  onToggle,
  openAll,
}: {
  company: CompanyRow;
  lights?: CompanyLights;
  groups: string[];
  busy: string;
  onToggle: (c: CompanyRow, i: ChecklistItem) => void;
  openAll: boolean;
}) {
  return (
    <article className="v2-company-card">
      <header>
        <h3>{c.name}</h3>
        <span className="v2-type">{typeName(c.person_type)}</span>
        <small>
          <span className="rfc">{c.rfc}</span>
          <span>Resp: {c.accountant || '—'}</span>
          <span className={c.overdue ? 'v11-progress is-overdue' : 'v11-progress'}>
            {c.done}/{c.total} hechas
          </span>
        </small>
      </header>
      {lights && <DocumentLights company={lights} />}
      <div className="v2-groups">
        {groups.map((g) => {
          const items = c.items.filter((i) => i.group === g);
          if (!items.length) return null;
          const { done, tone } = groupBar(items);
          return (
            <details key={g} className="v11-group v2-group" open={items.some((i) => i.overdue) || openAll}>
              <summary>
                <ChevronDown size={16} aria-hidden className="v11-chevron" />
                <span>{g}</span>
                <span className={'v11-group-count' + tone}>
                  {done}/{items.length}
                </span>
                <span className={'v2-bar' + tone} aria-hidden>
                  <span style={{ width: (done / items.length) * 100 + '%' }} />
                </span>
              </summary>
              {items.map((i) => (
                <Box
                  key={i.obligation_id}
                  item={i}
                  company={c}
                  busy={busy === c.id + i.obligation_id}
                  onToggle={onToggle}
                />
              ))}
            </details>
          );
        })}
      </div>
    </article>
  );
}

export default function ObligationChecklist({
  period,
  companyId,
  notify,
}: {
  period: string;
  companyId?: string;
  notify: (s: string) => void;
}) {
  const [year, month] = period.split('-').map(Number);
  const [data, setData] = useState<Checklist | null>(null);
  const [lights, setLights] = useState<Record<string, CompanyLights>>({});
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'cards' | 'matrix'>(() =>
    window.innerWidth >= 1024 && !companyId ? 'matrix' : 'cards',
  );
  const [responsible, setResponsible] = useState('');
  const [personType, setPersonType] = useState('');
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState('');
  const [reload, setReload] = useState(0);
  const [showCatalog, setShowCatalog] = useState(false);
  // Rediseño v2: cell of the matrix whose detail is shown on the side panel.
  const [selected, setSelected] = useState<{ company: string; obligation: string } | null>(null);
  const params = new URLSearchParams({
    year: String(year),
    month: String(month),
    ...(companyId ? { company_id: companyId } : {}),
    ...(responsible ? { responsible } : {}),
    ...(personType ? { person_type: personType } : {}),
    ...(pending ? { pending: 'true' } : {}),
  });
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setError('');
    api<Checklist>('/fiscal-control/checklist?' + params, 'GET', undefined, abort.signal)
      .then(setData)
      .catch((e) => !abort.signal.aborted && setError(e.message))
      .finally(() => !abort.signal.aborted && setLoading(false));
    api<{ companies: CompanyLights[] }>(
      '/integral/document-status' + (companyId ? '?company_id=' + companyId : ''),
      'GET',
      undefined,
      abort.signal,
    )
      .then((d) => setLights(Object.fromEntries(d.companies.map((c) => [c.company_id, c]))))
      .catch(() => setLights({}));
    return () => abort.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.toString(), reload]);

  async function toggle(company: CompanyRow, item: ChecklistItem) {
    setBusy(company.id + item.obligation_id);
    try {
      await api('/fiscal-control/checklist', 'PUT', {
        company_id: company.id,
        obligation_id: item.obligation_id,
        year,
        month,
        done: !item.done,
        revision: item.revision,
      });
      setReload((n) => n + 1);
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  const accountants = [
    ...new Map(
      (data?.companies || []).filter((c) => c.accountant_id).map((c) => [c.accountant_id!, c.accountant]),
    ).entries(),
  ];
  const groups = data?.groups || [];
  const used = (data?.catalog || []).filter((d) =>
    data?.companies.some((c) => c.items.some((i) => i.obligation_id === d.id)),
  );
  const s = data?.summary;
  const selectedCompany = selected ? data?.companies.find((c) => c.id === selected.company) : undefined;
  const selectedItem = selectedCompany?.items.find((i) => i.obligation_id === selected?.obligation);
  return (
    <div className="v11-checklist v2-obligations" aria-busy={loading}>
      <section className="v2-filters" aria-label="Vista y filtros de obligaciones">
        <div className="v2-filter-row">
          {!companyId && (
            <div className="v2-segmented" role="group" aria-label="Vista de obligaciones">
              <button type="button" aria-pressed={mode === 'cards'} onClick={() => setMode('cards')}>
                <LayoutGrid size={16} aria-hidden /> Vista tarjetas
              </button>
              <button type="button" aria-pressed={mode === 'matrix'} onClick={() => setMode('matrix')}>
                <Table2 size={16} aria-hidden /> Vista matriz
              </button>
            </div>
          )}
          {s && (
            <ul className="v2-totals" aria-label="Resumen del periodo">
              <li className="is-done">
                <CheckCircle2 size={16} aria-hidden /> Hechas <strong>{s.done}</strong>
                <span className="muted">/{s.total}</span>
              </li>
              <li>
                <Clock3 size={16} aria-hidden /> Pendientes <strong>{s.pending}</strong>
              </li>
              <li className="is-overdue">
                <AlertCircle size={16} aria-hidden /> Vencidas <strong>{s.overdue}</strong>
              </li>
              <li>
                <Building2 size={16} aria-hidden /> Empresas <strong>{data!.companies.length}</strong>
              </li>
            </ul>
          )}
        </div>
        <div className="v2-filter-row">
          {!companyId && (
            <>
              <select
                aria-label="Contador responsable"
                value={responsible}
                onChange={(e) => setResponsible(e.target.value)}
              >
                <option value="">Todos los contadores</option>
                {accountants.map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
              <select aria-label="Tipo de persona" value={personType} onChange={(e) => setPersonType(e.target.value)}>
                <option value="">Físicas y morales</option>
                <option value="Física">Personas físicas</option>
                <option value="Moral">Personas morales</option>
              </select>
              <button type="button" className="v2-chip" aria-pressed={pending} onClick={() => setPending((v) => !v)}>
                Con pendientes
              </button>
            </>
          )}
          <div className="v2-filter-actions">
            <button
              type="button"
              className={stitchButton}
              onClick={() =>
                downloadApi('/fiscal-control/checklist.xlsx?' + params, `obligaciones_${period}.xlsx`).catch((e) =>
                  notify(e.message),
                )
              }
            >
              <Download size={16} aria-hidden /> Excel
            </button>
            {!companyId && (
              <button
                type="button"
                className={showCatalog ? stitchPrimary : stitchButton}
                aria-pressed={showCatalog}
                onClick={() => setShowCatalog((v) => !v)}
              >
                Catálogo
              </button>
            )}
          </div>
        </div>
        <ul className="v2-cell-legend" aria-label="Leyenda de la matriz">
          <li>
            <span className="v2-cell is-done" aria-hidden>
              <CheckCircle2 size={15} />
            </span>
            Hecha
          </li>
          <li>
            <span className="v2-cell" aria-hidden>
              <Clock3 size={15} />
            </span>
            Pendiente
          </li>
          <li>
            <span className="v2-cell is-overdue" aria-hidden>
              <AlertCircle size={15} />
            </span>
            Vencida
          </li>
          <li>
            <span className="v2-cell is-na" aria-hidden>
              <MinusCircle size={15} />
            </span>
            No aplica
          </li>
        </ul>
      </section>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {loading && !data && <p role="status">Consultando obligaciones…</p>}
      {data && data.companies.length === 0 && (
        <p className="v2-empty muted">
          No hay obligaciones de constancia asignadas en este periodo. Se proponen al registrar o actualizar una empresa
          con su Constancia de Situación Fiscal.
        </p>
      )}
      {data && mode === 'cards' && data.companies.length > 0 && (
        <div className="v2-company-cards">
          {data.companies.map((c) => (
            <CompanyCard
              key={c.id}
              company={c}
              lights={lights[c.id]}
              groups={groups}
              busy={busy}
              onToggle={toggle}
              openAll={!!companyId}
            />
          ))}
        </div>
      )}
      {data && mode === 'matrix' && data.companies.length > 0 && (
        <div className={'v2-matrix-layout' + (selectedItem ? ' has-detail' : '')}>
          <div className="v11-matrix-scroll v2-matrix-scroll">
            <table className="v11-matrix v2-matrix">
              <thead>
                <tr>
                  <th rowSpan={2} scope="col">
                    Empresa / RFC
                  </th>
                  {groups.map((g) => {
                    const n = used.filter((d) => d.group === g).length;
                    return n ? (
                      <th key={g} colSpan={n} scope="colgroup">
                        {g}
                      </th>
                    ) : null;
                  })}
                  <th rowSpan={2} scope="col">
                    Avance
                  </th>
                </tr>
                <tr>
                  {groups.flatMap((g) =>
                    used
                      .filter((d) => d.group === g)
                      .map((d) => (
                        <th key={d.id} scope="col" title={d.official_name}>
                          {d.short_name}
                        </th>
                      )),
                  )}
                </tr>
              </thead>
              <tbody>
                {data.companies.map((c) => (
                  <tr key={c.id}>
                    <th scope="row">
                      {c.name}
                      <small className="rfc">{c.rfc}</small>
                    </th>
                    {groups.flatMap((g) =>
                      used
                        .filter((d) => d.group === g)
                        .map((d) => {
                          const item = c.items.find((i) => i.obligation_id === d.id);
                          if (!item)
                            return (
                              <td key={d.id} className="v11-na">
                                <span className="v2-cell is-na" title="No aplica">
                                  <MinusCircle size={15} aria-hidden />
                                  <span className="sr-only">No aplica</span>
                                </span>
                              </td>
                            );
                          const isSelected = selected?.company === c.id && selected.obligation === d.id;
                          const select = () => setSelected({ company: c.id, obligation: d.id });
                          if (item.not_applicable)
                            return (
                              <td key={d.id} className="v11-na">
                                <button
                                  type="button"
                                  className={'v2-cell is-na' + (isSelected ? ' is-selected' : '')}
                                  aria-label={`${d.official_name}, ${c.name}: no aplica. Ver detalle`}
                                  onClick={select}
                                >
                                  <MinusCircle size={15} aria-hidden />
                                </button>
                              </td>
                            );
                          const state = item.done ? 'hecha' : item.overdue ? 'vencida' : 'pendiente';
                          return (
                            <td
                              key={d.id}
                              className={item.done ? 'is-done' : item.overdue ? 'is-overdue' : ''}
                              onClick={select}
                            >
                              <label
                                className={
                                  'v2-cell' +
                                  (item.done ? ' is-done' : item.overdue ? ' is-overdue' : '') +
                                  (isSelected ? ' is-selected' : '')
                                }
                                title={item.due_date ? 'Vence ' + date(item.due_date) : d.official_name}
                              >
                                <input
                                  type="checkbox"
                                  aria-label={`${d.official_name}, ${c.name}: ${state}`}
                                  checked={item.done}
                                  disabled={busy === c.id + d.id}
                                  onChange={() => toggle(c, item)}
                                  onFocus={select}
                                />
                                {item.done ? (
                                  <CheckCircle2 size={15} aria-hidden />
                                ) : item.overdue ? (
                                  <AlertCircle size={15} aria-hidden />
                                ) : (
                                  <Clock3 size={15} aria-hidden />
                                )}
                              </label>
                            </td>
                          );
                        }),
                    )}
                    <td
                      className={'v2-progress-cell ' + (c.overdue ? 'is-overdue' : c.done === c.total ? 'is-done' : '')}
                    >
                      {c.done}/{c.total}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {selectedItem && selectedCompany && (
            <aside className="v2-detail" aria-label="Detalle de la obligación">
              <header>
                <span
                  className={
                    'v2-state ' +
                    (selectedItem.not_applicable
                      ? 'is-na'
                      : selectedItem.done
                        ? 'is-done'
                        : selectedItem.overdue
                          ? 'is-overdue'
                          : '')
                  }
                >
                  {selectedItem.not_applicable ? (
                    <MinusCircle size={14} aria-hidden />
                  ) : selectedItem.done ? (
                    <CheckCircle2 size={14} aria-hidden />
                  ) : selectedItem.overdue ? (
                    <AlertCircle size={14} aria-hidden />
                  ) : (
                    <Clock3 size={14} aria-hidden />
                  )}
                  {selectedItem.not_applicable
                    ? 'No aplica'
                    : selectedItem.done
                      ? 'Hecha'
                      : selectedItem.overdue
                        ? 'Vencida'
                        : 'Pendiente'}
                </span>
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Cerrar detalle"
                  onClick={() => setSelected(null)}
                >
                  <X size={18} />
                </button>
              </header>
              <h3>{selectedItem.official_name}</h3>
              <dl>
                <dt>Empresa y RFC</dt>
                <dd>
                  {selectedCompany.name}
                  <span className="rfc">{selectedCompany.rfc}</span>
                </dd>
                <dt>Fecha de vencimiento</dt>
                <dd>{selectedItem.due_date ? date(selectedItem.due_date) : selectedItem.due_text || '—'}</dd>
                <dt>Periodicidad</dt>
                <dd>{CADENCE[selectedItem.cadence] || selectedItem.cadence || '—'}</dd>
                <dt>Registro de cumplimiento</dt>
                <dd>
                  {selectedItem.marked_by && selectedItem.marked_at
                    ? `${selectedItem.marked_by} · ${new Date(selectedItem.marked_at).toLocaleString('es-MX')}`
                    : 'Sin registrar'}
                </dd>
              </dl>
              {!selectedItem.not_applicable && (
                <button
                  type="button"
                  className={selectedItem.done ? stitchButton : stitchPrimary}
                  disabled={busy === selectedCompany.id + selectedItem.obligation_id}
                  onClick={() => toggle(selectedCompany, selectedItem)}
                >
                  {selectedItem.done ? 'Marcar como pendiente' : 'Marcar como hecha'}
                </button>
              )}
            </aside>
          )}
        </div>
      )}
      {showCatalog && <ObligationCatalog notify={notify} />}
      <p className="muted small">
        Control interno del despacho: las fechas de vencimiento se calculan con la regla de cada obligación (no se
        recorren por días inhábiles) y nada se valida ante el SAT.
      </p>
    </div>
  );
}
