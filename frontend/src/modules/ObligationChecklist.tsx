import { useEffect, useState } from 'react';
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Download,
  LayoutGrid,
  List,
  ListChecks,
  MinusCircle,
  Search,
  ShieldCheck,
  Table2,
} from 'lucide-react';
import { api, downloadApi } from '../api';
import { Kpi } from '../components/ui';
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

/** Summary of /integral/document-status (Plan v1.1, Cambio 1) used by the panel KPIs. */
type DocSummary = {
  active_rfcs: number;
  physical: number;
  moral: number;
  sat: { positive: number; negative: number; none: number; percent: number };
  expiring: { days: number; count: number };
};
const MONTHS = [
  'Enero',
  'Febrero',
  'Marzo',
  'Abril',
  'Mayo',
  'Junio',
  'Julio',
  'Agosto',
  'Septiembre',
  'Octubre',
  'Noviembre',
  'Diciembre',
];

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

export default function ObligationChecklist({
  period,
  companyId,
  notify,
  variant,
  onPeriod,
}: {
  period: string;
  companyId?: string;
  notify: (s: string) => void;
  /** Rediseño v2: «panel» is the Panel de empresas (KPIs, filters, cards or list); same data and boxes. */
  variant?: 'panel';
  onPeriod?: (period: string) => void;
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
  const [docSummary, setDocSummary] = useState<DocSummary | null>(null);
  const [query, setQuery] = useState('');
  const [view, setView] = useState<'cards' | 'list'>('cards');
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
    api<{ companies: CompanyLights[]; summary?: DocSummary }>(
      '/integral/document-status' + (companyId ? '?company_id=' + companyId : ''),
      'GET',
      undefined,
      abort.signal,
    )
      .then((d) => {
        setLights(Object.fromEntries(d.companies.map((c) => [c.company_id, c])));
        setDocSummary(d.summary || null);
      })
      .catch(() => {
        setLights({});
        setDocSummary(null);
      });
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
  if (variant === 'panel') {
    const q = query.trim().toLowerCase();
    const shown = (data?.companies || []).filter((c) => !q || (c.name + ' ' + c.rfc).toLowerCase().includes(q));
    const totalCompanies = docSummary?.active_rfcs ?? Object.keys(lights).length;
    const nowYear = new Date().getFullYear();
    const years = Array.from({ length: nowYear + 1 - 2019 }, (_, i) => nowYear + 1 - i);
    const setPeriodPart = (y: number, m: number) => onPeriod?.(`${y}-${String(m).padStart(2, '0')}`);
    const sat = docSummary?.sat;
    const hasOpinions = !!sat && sat.positive + sat.negative > 0;
    const groupBar = (items: ChecklistItem[]) => {
      const done = items.filter((i) => i.done).length;
      const tone = items.some((i) => i.overdue) ? ' is-overdue' : done === items.length ? ' is-done' : '';
      return { done, tone };
    };
    // List view: only the tax families that some visible company has in the period.
    const listGroups = groups.filter((g) => shown.some((c) => c.items.some((i) => i.group === g)));
    const typeName = (t: string) => (t === 'Física' ? 'Persona física' : t === 'Moral' ? 'Persona moral' : t || '—');
    return (
      <div className="v11-checklist v2-panel" aria-busy={loading}>
        <div className="v2-kpis">
          <Kpi
            label="Empresas activas"
            icon={<Building2 size={18} aria-hidden />}
            value={docSummary ? docSummary.active_rfcs : '—'}
            detail={
              docSummary ? `${docSummary.physical} físicas · ${docSummary.moral} morales` : 'Sin datos del semáforo'
            }
          />
          <Kpi
            label="Opinión SAT positiva"
            icon={<ShieldCheck size={18} aria-hidden />}
            value={hasOpinions ? sat!.percent + '%' : '—'}
            detail={
              sat
                ? `${sat.positive} positivas · ${sat.negative} negativas · ${sat.none} sin opinión`
                : 'Sin datos del semáforo'
            }
            tone={hasOpinions ? (sat!.negative ? 'red' : 'green') : 'neutral'}
          />
          <Kpi
            label={'Obligaciones de ' + MONTHS[month - 1].toLowerCase()}
            icon={<ListChecks size={18} aria-hidden />}
            value={
              s && s.total ? (
                <>
                  {s.done}/{s.total} <small>hechas</small>
                </>
              ) : (
                '—'
              )
            }
            detail={
              s && s.total
                ? `${s.pending} pendientes · ${s.overdue} vencidas`
                : 'Sin obligaciones asignadas en el periodo'
            }
          >
            {s && s.total > 0 && (
              <span className="v2-bar" role="img" aria-label={`${Math.round((s.done / s.total) * 100)}% hechas`}>
                <span style={{ width: (s.done / s.total) * 100 + '%' }} />
              </span>
            )}
          </Kpi>
          <Kpi
            label="Documentos por vencer"
            icon={<Clock3 size={18} aria-hidden />}
            value={docSummary ? docSummary.expiring.count : '—'}
            detail={
              docSummary
                ? `FIEL, opiniones y constancias en los próximos ${docSummary.expiring.days} días`
                : 'Sin datos del semáforo'
            }
            tone={docSummary?.expiring.count ? 'amber' : 'neutral'}
          />
        </div>
        <section className="v2-filters" aria-label="Filtros del panel">
          <div className="v2-filter-row">
            <select
              aria-label="Año"
              value={year}
              disabled={!onPeriod}
              onChange={(e) => setPeriodPart(Number(e.target.value), month)}
            >
              {years.map((y) => (
                <option key={y} value={y}>
                  Año: {y}
                </option>
              ))}
            </select>
            <select
              aria-label="Mes"
              value={month}
              disabled={!onPeriod}
              onChange={(e) => setPeriodPart(year, Number(e.target.value))}
            >
              {MONTHS.map((m, i) => (
                <option key={m} value={i + 1}>
                  Mes: {m}
                </option>
              ))}
            </select>
            {!companyId && (
              <select
                aria-label="Contador responsable"
                value={responsible}
                onChange={(e) => setResponsible(e.target.value)}
              >
                <option value="">Contador: Todos</option>
                {accountants.map(([id, name]) => (
                  <option key={id} value={id}>
                    Contador: {name}
                  </option>
                ))}
              </select>
            )}
            <label className="v2-search">
              <Search size={16} aria-hidden />
              <input
                type="search"
                aria-label="Buscar por nombre o RFC"
                placeholder="Buscar por nombre o RFC…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
          </div>
          <div className="v2-filter-row">
            {!companyId && (
              <div className="v2-chips" role="group" aria-label="Filtros rápidos">
                <button type="button" className="v2-chip" aria-pressed={pending} onClick={() => setPending((v) => !v)}>
                  Con pendientes
                </button>
                <button
                  type="button"
                  className="v2-chip"
                  aria-pressed={personType === 'Moral'}
                  onClick={() => setPersonType((v) => (v === 'Moral' ? '' : 'Moral'))}
                >
                  Morales
                </button>
                <button
                  type="button"
                  className="v2-chip"
                  aria-pressed={personType === 'Física'}
                  onClick={() => setPersonType((v) => (v === 'Física' ? '' : 'Física'))}
                >
                  Físicas
                </button>
              </div>
            )}
            <div className="v2-filter-actions">
              <div className="v2-segmented" role="group" aria-label="Vista del panel">
                <button type="button" aria-pressed={view === 'cards'} onClick={() => setView('cards')}>
                  <LayoutGrid size={16} aria-hidden /> Tarjetas
                </button>
                <button type="button" aria-pressed={view === 'list'} onClick={() => setView('list')}>
                  <List size={16} aria-hidden /> Lista
                </button>
              </div>
              <button
                type="button"
                className={stitchButton}
                onClick={() =>
                  downloadApi('/fiscal-control/checklist.xlsx?' + params, `obligaciones_${period}.xlsx`).catch((e) =>
                    notify(e.message),
                  )
                }
              >
                <Download size={16} aria-hidden /> Exportar a Excel
              </button>
            </div>
          </div>
        </section>
        {error && (
          <p role="alert" className="error-banner">
            {error}
          </p>
        )}
        {loading && !data && <p role="status">Consultando empresas y obligaciones…</p>}
        {data && shown.length === 0 && (
          <p className="v2-empty muted">
            {data.companies.length
              ? 'Ninguna empresa coincide con la búsqueda.'
              : 'No hay obligaciones asignadas en este periodo. Se proponen al registrar o actualizar una empresa con su Constancia de Situación Fiscal.'}
          </p>
        )}
        {data && view === 'cards' && shown.length > 0 && (
          <div className="v2-company-cards">
            {shown.map((c) => (
              <article key={c.id} className="v2-company-card">
                <header>
                  <h3>{c.name}</h3>
                  <span className="v2-type">{typeName(c.person_type)}</span>
                  <small>
                    <span className="rfc">{c.rfc}</span>
                    <span>Resp: {c.accountant || '—'}</span>
                  </small>
                </header>
                {lights[c.id] && <DocumentLights company={lights[c.id]} />}
                <div className="v2-groups">
                  {groups.map((g) => {
                    const items = c.items.filter((i) => i.group === g);
                    if (!items.length) return null;
                    const { done, tone } = groupBar(items);
                    return (
                      <details
                        key={g}
                        className="v11-group v2-group"
                        open={items.some((i) => i.overdue) || !!companyId}
                      >
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
                            onToggle={toggle}
                          />
                        ))}
                      </details>
                    );
                  })}
                </div>
              </article>
            ))}
          </div>
        )}
        {data && view === 'list' && shown.length > 0 && (
          <div className="v2-list-scroll">
            <table className="v2-list">
              <thead>
                <tr>
                  <th scope="col">Empresa</th>
                  <th scope="col">Semáforo</th>
                  {listGroups.map((g) => (
                    <th scope="col" key={g}>
                      {g}
                    </th>
                  ))}
                  <th scope="col">Avance</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((c) => (
                  <tr key={c.id}>
                    <th scope="row">
                      {c.name}
                      <small className="rfc">{c.rfc}</small>
                    </th>
                    <td>{lights[c.id] ? <DocumentLights company={lights[c.id]} compact /> : '—'}</td>
                    {listGroups.map((g) => {
                      const items = c.items.filter((i) => i.group === g);
                      if (!items.length) return <td key={g}>—</td>;
                      const { done, tone } = groupBar(items);
                      return (
                        <td key={g} className={'v11-group-count' + tone}>
                          {done}/{items.length}
                        </td>
                      );
                    })}
                    <td className={c.overdue ? 'v11-progress is-overdue' : 'v11-progress'}>
                      {c.done}/{c.total}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <footer className="v2-legend">
          <ul aria-label="Leyenda del semáforo">
            <li className="is-green">
              <CheckCircle2 size={16} aria-hidden /> Vigente
            </li>
            <li className="is-amber">
              <Clock3 size={16} aria-hidden /> Por vencer
            </li>
            <li className="is-red">
              <AlertCircle size={16} aria-hidden /> Vencido o negativo
            </li>
            <li className="is-gray">
              <MinusCircle size={16} aria-hidden /> Sin documento o no aplica
            </li>
          </ul>
          {data && (
            <span>
              Mostrando {shown.length} de {totalCompanies} empresas activas
              {totalCompanies > data.companies.length && ' · las demás no tienen obligaciones asignadas en el periodo'}
            </span>
          )}
        </footer>
      </div>
    );
  }

  return (
    <div className="v11-checklist" aria-busy={loading}>
      <div className="toolbar">
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
            <label className="check-option">
              <input type="checkbox" checked={pending} onChange={(e) => setPending(e.target.checked)} /> Con pendientes
            </label>
          </>
        )}
        <div className="actions">
          {!companyId && (
            <>
              <button
                className={mode === 'cards' ? stitchPrimary : stitchButton}
                aria-pressed={mode === 'cards'}
                onClick={() => setMode('cards')}
              >
                <LayoutGrid size={16} aria-hidden /> Tarjetas
              </button>
              <button
                className={mode === 'matrix' ? stitchPrimary : stitchButton}
                aria-pressed={mode === 'matrix'}
                onClick={() => setMode('matrix')}
              >
                <Table2 size={16} aria-hidden /> Matriz
              </button>
            </>
          )}
          <button
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
              className={showCatalog ? stitchPrimary : stitchButton}
              aria-pressed={showCatalog}
              onClick={() => setShowCatalog((v) => !v)}
            >
              Catálogo
            </button>
          )}
        </div>
      </div>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {loading && !data && <p role="status">Consultando obligaciones…</p>}
      {s && (
        <div className="kpi-grid four">
          <Kpi label="Hechas" value={`${s.done}/${s.total}`} detail="Obligaciones del periodo" tone="green" />
          <Kpi label="Pendientes" value={s.pending} detail="Sin marcar como hechas" tone="amber" />
          <Kpi label="Vencidas" value={s.overdue} detail="Sin marcar después de su vencimiento" tone="red" />
          <Kpi label="Empresas" value={data!.companies.length} detail="Dentro de los filtros" />
        </div>
      )}
      {data && data.companies.length === 0 && (
        <p className="muted">
          No hay obligaciones de constancia asignadas en este periodo. Se proponen al registrar o actualizar una empresa
          con su Constancia de Situación Fiscal.
        </p>
      )}
      {data && mode === 'cards' && (
        <div className="v11-company-cards">
          {data.companies.map((c) => (
            <article key={c.id} className="v11-company-card">
              <header>
                <div>
                  <h3>{c.name}</h3>
                  <small className="muted">
                    {c.rfc} · {c.accountant}
                  </small>
                </div>
                <strong className={c.overdue ? 'v11-progress is-overdue' : 'v11-progress'}>
                  {c.done}/{c.total}
                </strong>
              </header>
              {lights[c.id] && <DocumentLights company={lights[c.id]} compact />}
              {groups.map((g) => {
                const items = c.items.filter((i) => i.group === g);
                if (!items.length) return null;
                const done = items.filter((i) => i.done).length;
                return (
                  <details key={g} className="v11-group" open={items.some((i) => i.overdue) || !!companyId}>
                    <summary>
                      <ChevronDown size={16} aria-hidden className="v11-chevron" />
                      <span>{g}</span>
                      <span
                        className={
                          'v11-group-count' +
                          (items.some((i) => i.overdue) ? ' is-overdue' : done === items.length ? ' is-done' : '')
                        }
                      >
                        {done}/{items.length}
                      </span>
                    </summary>
                    {items.map((i) => (
                      <Box
                        key={i.obligation_id}
                        item={i}
                        company={c}
                        busy={busy === c.id + i.obligation_id}
                        onToggle={toggle}
                      />
                    ))}
                  </details>
                );
              })}
            </article>
          ))}
        </div>
      )}
      {data && mode === 'matrix' && data.companies.length > 0 && (
        <div className="v11-matrix-scroll">
          <table className="v11-matrix">
            <thead>
              <tr>
                <th rowSpan={2} scope="col">
                  Empresa
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
                    <small className="muted"> {c.rfc}</small>
                  </th>
                  {groups.flatMap((g) =>
                    used
                      .filter((d) => d.group === g)
                      .map((d) => {
                        const item = c.items.find((i) => i.obligation_id === d.id);
                        if (!item)
                          return (
                            <td key={d.id} className="v11-na" aria-label="No aplica">
                              —
                            </td>
                          );
                        return (
                          <td key={d.id} className={item.done ? 'is-done' : item.overdue ? 'is-overdue' : ''}>
                            <input
                              type="checkbox"
                              aria-label={`${d.official_name}, ${c.name}: ${item.done ? 'hecha' : item.overdue ? 'vencida' : 'pendiente'}`}
                              title={item.due_date ? 'Vence ' + date(item.due_date) : d.official_name}
                              checked={item.done}
                              disabled={busy === c.id + d.id}
                              onChange={() => toggle(c, item)}
                            />
                          </td>
                        );
                      }),
                  )}
                  <td className={c.overdue ? 'is-overdue' : c.done === c.total ? 'is-done' : ''}>
                    {c.done}/{c.total}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
