import DocumentLights, { type CompanyLights } from './DocumentLights';
import { useState, useEffect } from 'react';
import { canRegisterCompanies, csfIsStale, responsibleName } from '../permissions';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Plus, Eye, Search, Download, CalendarDays, FolderOpen, Upload, ArrowLeft } from 'lucide-react';
import { api, csv, today } from '../api';
import { Badge, Empty, Heading } from '../components/ui';
import Documents from './Documents';
import IntegralDashboard from './IntegralDashboard';
import CompanyImporter from './CompanyImporter';
import FiscalControl from './FiscalControl';
import ObligationChecklist from './ObligationChecklist';
import DashboardSummary from './DashboardSummary';
import CompanyLightsList from './CompanyLightsList';
import { CompanySwitcher, CompanyViews } from './CompanyHeader';
import { useFiscalRead, fiscalStatus, exportFiscal, type Summary } from './fiscalRead';
import { confirmDiscard } from '../navigationGuard';
import { DASHBOARD_TABS, dashboardTarget, dashboardUrl, type DashboardTab } from '../companyNavigation';
import type { State, Company } from '../types';
export const statusOf = (_c: Company, _state: State, _period?: string, summary?: Summary) => fiscalStatus(summary);
export const toneOf = (s: string) => (s === 'Crítico' ? 'red' : s === 'Sin pendientes' ? 'green' : 'amber');
// Redirects (Credenciales, alertas, tareas) are resolved by the route before this page renders.
const target = (params: URLSearchParams) => {
  const t = dashboardTarget(params.get('tab'), params.get('sub'), params.get('vista'));
  return 'tab' in t ? t : { tab: 'resumen' as DashboardTab, sub: '' };
};
const validPeriod = (value: string | null) => (/^20\d{2}-(0[1-9]|1[0-2])$/.test(value || '') ? value! : '');
// Directory filters kept in the URL only when they differ from the default.
const DIRECTORY_DEFAULTS: Record<string, string> = {
  query: '',
  responsible: '',
  status: '',
  archive: 'active',
  sort: 'name',
};

/** Dashboard principal (Workspace Fiscal › Empresas): Resumen, Empresas, Documentos y Obligaciones. */
export default function Companies({
  state,
  refresh,
  notify,
}: {
  state: State;
  refresh: () => Promise<void>;
  notify: (m: string) => void;
}) {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { tab, sub } = target(params);
  const section = DASHBOARD_TABS.find((t) => t.id === tab)!;
  // Opened for one company (Bloque 3): Resumen and Obligaciones show its switcher.
  const focused = params.get('company_id') || '';
  // Un solo periodo para Resumen y Obligaciones; se conserva al pasar por las demás pestañas.
  const [period, setPeriod] = useState(() => validPeriod(params.get('period')) || today().slice(0, 7));
  const [query, setQuery] = useState(params.get('query') || '');
  // Responsible by user (Bloque 2): '' all, 'mine', 'none' (no linked user) or a user id.
  const [responsible, setResponsible] = useState(params.get('responsible') || '');
  const [status, setStatus] = useState(params.get('status') || '');
  const [page, setPage] = useState(1);
  const [archive, setArchive] = useState(params.get('archive') || 'active'),
    [sort, setSort] = useState(params.get('sort') || 'name');
  const directoryOpen = tab === 'empresas' && sub === 'directorio';
  const { data: fiscal, error: fiscalError } = useFiscalRead(period, undefined, archive !== 'active');
  useEffect(() => {
    document.title = 'Dashboard principal · ContaSuite';
    return () => {
      document.title = 'ContaSuite · Gestión contable inteligente';
    };
  }, []);
  // Plan v1.1: document traffic light of every visible company, shown compact in the directory.
  const [lights, setLights] = useState<Record<string, CompanyLights>>({});
  useEffect(() => {
    if (!directoryOpen) return;
    const abort = new AbortController();
    api<{ companies: CompanyLights[] }>('/integral/document-status', 'GET', undefined, abort.signal)
      .then((d) => setLights(Object.fromEntries(d.companies.map((c) => [c.company_id, c]))))
      .catch(() => !abort.signal.aborted && setLights({}));
    return () => abort.abort();
  }, [state.companies.length, directoryOpen]);
  const [directory, setDirectory] = useState<Company[]>([]),
    [directoryError, setDirectoryError] = useState(''),
    [directoryLoading, setDirectoryLoading] = useState(false);
  useEffect(() => {
    const abort = new AbortController();
    setDirectoryLoading(true);
    setDirectoryError('');
    const q = new URLSearchParams({ query, responsible, archive, sort });
    api<{ companies: Company[] }>('/company-lifecycle?' + q, 'GET', undefined, abort.signal)
      .then((d) => setDirectory(d.companies))
      .catch((e) => {
        if (!abort.signal.aborted) {
          setDirectory([]);
          setDirectoryError(e.message);
        }
      })
      .finally(() => {
        if (!abort.signal.aborted) setDirectoryLoading(false);
      });
    return () => abort.abort();
  }, [query, responsible, archive, sort, state.companies]);
  // The URL always names the canonical tab and sub-tab (old names are rewritten) and the page filters.
  useEffect(() => {
    setParams(
      (previous) => {
        const q = new URLSearchParams(previous);
        q.set('tab', tab);
        if (sub) q.set('sub', sub);
        else q.delete('sub');
        q.delete('vista');
        q.set('period', period);
        for (const [key, value] of Object.entries({ query, responsible, status, archive, sort }))
          if (value !== DIRECTORY_DEFAULTS[key]) q.set(key, value);
          else q.delete(key);
        return q;
      },
      { replace: true },
    );
    // setParams changes identity on every URL change (React Router 7); as a dependency this URL sync
    // would re-run after its own write. It only has to follow the page state below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, sub, period, query, responsible, status, archive, sort]);
  const go = (next: DashboardTab, nextSub = '') => {
    if (!confirmDiscard()) return;
    const q = new URLSearchParams({ tab: next });
    const first = nextSub || DASHBOARD_TABS.find((t) => t.id === next)?.subs[0]?.id || '';
    if (first) q.set('sub', first);
    q.set('period', period);
    if (focused && (next === 'resumen' || next === 'obligaciones')) q.set('company_id', focused);
    setParams(q);
  };
  const activeCompanies = state.companies.filter((c) => c.archived !== true).length;
  const all = directory;
  const list = all.filter((c) => !status || statusOf(c, state, period, fiscal?.company_summaries[c.id]) === status);
  const pages = Math.max(1, Math.ceil(list.length / 10));
  const current = Math.min(page, pages);
  const canRegister = canRegisterCompanies(state.current_user);
  const exportCompanies = () =>
    csv('Empresas_ContaSuite.csv', [
      ['Razón social', 'RFC', 'Tipo', 'Régimen', 'Contador', 'Estado interno'],
      ...list.map((c) => [
        c.name,
        c.rfc,
        c.person_type,
        c.regime,
        responsibleName(c, state.responsibles),
        statusOf(c, state, period, fiscal?.company_summaries[c.id]),
      ]),
    ]);
  const dossierLink = (c: Company) =>
    '/empresas/' + c.id + '?' + new URLSearchParams({ period, query, responsible, status, archive, sort });
  return (
    <>
      <Heading
        eyebrow="CENTRO DE CONTROL FISCAL"
        title="Dashboard principal"
        description={section.subtitle}
        actions={
          <>
            {directoryOpen && canRegister && (
              <Link className="btn" to={dashboardUrl('empresas', 'importar')}>
                <Upload size={16} />
                Importar
              </Link>
            )}
            {canRegister && (
              <Link className="btn primary" to="/empresas/nueva">
                <Plus size={17} />
                Registrar empresa
              </Link>
            )}
          </>
        }
      />
      <div className="v2-dashboard-tabs">
        <nav className="tabs card" aria-label="Pestañas del Dashboard principal">
          {DASHBOARD_TABS.map((t) => (
            <Link
              key={t.id}
              to={dashboardUrl(t.id, '', { period })}
              className={t.id === tab ? 'active' : ''}
              aria-current={t.id === tab ? 'page' : undefined}
              onClick={(e) => {
                e.preventDefault();
                go(t.id);
              }}
            >
              {t.label}
              {t.id === 'empresas' && <span>{activeCompanies}</span>}
            </Link>
          ))}
        </nav>
        {section.period && (
          <label className="period-control">
            <CalendarDays size={17} />
            <span>
              <small>PERIODO</small>
              <input
                aria-label="Periodo"
                type="month"
                value={period}
                onChange={(e) => {
                  if (validPeriod(e.target.value) && confirmDiscard()) setPeriod(e.target.value);
                }}
              />
            </span>
          </label>
        )}
      </div>
      {section.subs.length > 0 && (
        <nav className="tabs card subtabs" aria-label={'Subpestañas de ' + section.label}>
          {section.subs.map((v) => (
            <Link
              key={v.id}
              to={dashboardUrl(tab, v.id, { period })}
              className={v.id === sub ? 'active' : ''}
              aria-current={v.id === sub ? 'page' : undefined}
              onClick={(e) => {
                e.preventDefault();
                go(tab, v.id);
              }}
            >
              {v.label}
            </Link>
          ))}
        </nav>
      )}
      {focused && (tab === 'resumen' || tab === 'obligaciones') && (
        <div className="dossier-topbar">
          <CompanySwitcher
            companies={state.companies}
            companyId={focused}
            onChange={(id) => {
              if (!confirmDiscard()) return;
              const q = new URLSearchParams(params);
              q.set('company_id', id);
              setParams(q);
            }}
          />
          <CompanyViews
            current={tab === 'resumen' ? 'Dashboard' : 'Obligaciones'}
            companyId={focused}
            period={period}
          />
        </div>
      )}
      {tab === 'resumen' ? (
        <DashboardSummary
          key={focused}
          state={state}
          period={period}
          companyId={focused || undefined}
          notify={notify}
        />
      ) : tab === 'empresas' && sub === 'importar' ? (
        <>
          <div className="actions section-actions">
            <button className="btn" onClick={() => navigate(dashboardUrl('empresas', 'directorio'))}>
              <ArrowLeft size={16} />
              Volver al directorio
            </button>
          </div>
          <CompanyImporter state={state} />
        </>
      ) : tab === 'empresas' && sub === 'calidad' ? (
        <IntegralDashboard state={state} period={period} view="Calidad de datos" />
      ) : tab === 'documentos' && sub === 'semaforo' ? (
        <CompanyLightsList mode="semaforo" userId={state.current_user.id} />
      ) : tab === 'documentos' && sub === 'opiniones' ? (
        <>
          <CompanyLightsList mode="opiniones" userId={state.current_user.id} />
          <IntegralDashboard state={state} period={period} view="Opiniones de cumplimiento" />
        </>
      ) : tab === 'documentos' ? (
        <>
          <div className="card">
            <div className="card-title">
              <div>
                <h2>Expedientes digitales</h2>
                <p>Documentos adjuntos y rutas de archivo por contribuyente.</p>
              </div>
            </div>
            {all.length ? (
              <div className="dossier-grid">
                {all.map((c) => (
                  <Link className="dossier-card" key={c.id} to={'/empresas/' + c.id + '?tab=Documentos'}>
                    <FolderOpen size={27} />
                    <h3>{c.name}</h3>
                    <p className="rfc">{c.rfc}</p>
                    <small>{state.document_counts[c.id] ?? 0} documentos adjuntos</small>
                    <p className="path-text">{c.folder || 'Ruta local pendiente de configurar'}</p>
                    <span>Abrir expediente →</span>
                  </Link>
                ))}
              </div>
            ) : (
              <Empty title="Sin expedientes" />
            )}
          </div>
          <Documents notify={notify} refresh={refresh} />
        </>
      ) : tab === 'obligaciones' && sub === 'cfdi' ? (
        <IntegralDashboard key={focused} state={state} period={period} view="Seguimiento CFDI" />
      ) : tab === 'obligaciones' && sub === 'calendario' ? (
        <>
          <div className="actions section-actions">
            <button className="btn" disabled={!fiscal} onClick={() => fiscal && exportFiscal(fiscal, period)}>
              <Download size={16} />
              Obligaciones del periodo CSV
            </button>
          </div>
          <FiscalControl state={state} period={period} notify={notify} companyId={focused || undefined} />
        </>
      ) : tab === 'obligaciones' ? (
        <ObligationChecklist
          key={'matriz' + focused}
          period={period}
          companyId={focused || undefined}
          notify={notify}
        />
      ) : (
        <section className="card directory">
          {directoryLoading && <p role="status">Cargando directorio…</p>}
          {directoryError && (
            <p role="alert" className="error-banner">
              {directoryError}
            </p>
          )}
          {fiscalError && (
            <p role="alert" className="error-banner">
              {fiscalError}
            </p>
          )}
          <div className="toolbar">
            <label>
              Archivo
              <select
                aria-label="Estado de archivo"
                value={archive}
                onChange={(e) => {
                  setArchive(e.target.value);
                  setPage(1);
                }}
              >
                <option value="active">Activas</option>
                <option value="archived">Archivadas</option>
                <option value="all">Todas</option>
              </select>
            </label>
            <label>
              Ordenar
              <select aria-label="Ordenar empresas" value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="name">Nombre</option>
                <option value="rfc">RFC</option>
                <option value="accountant">Contador</option>
              </select>
            </label>
            <div className="search-field">
              <Search size={17} />
              <input
                aria-label="Buscar empresa"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPage(1);
                }}
                placeholder="Filtrar el directorio por empresa, RFC o nombre comercial…"
              />
            </div>
            <select
              aria-label="Contador responsable"
              value={responsible}
              onChange={(e) => {
                setResponsible(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Todos los responsables</option>
              {state.current_user.role === 'contador' && <option value="mine">Mis empresas</option>}
              <option value="none">Sin responsable</option>
              {(state.responsibles || []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.display_name + (r.enabled ? '' : ' (inactivo)')}
                </option>
              ))}
            </select>
            <select
              aria-label="Estado de empresa"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Todos los estados</option>
              {['Sin información', 'Sin pendientes', 'Requiere revisión', 'Crítico'].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
            <button className="btn" onClick={exportCompanies}>
              <Download size={15} />
              Exportar
            </button>
          </div>
          {directoryLoading || directoryError ? null : list.length ? (
            <div className="table-wrap scroll sticky-actions">
              <table>
                <thead>
                  <tr>
                    <th>Empresa / Razón social</th>
                    <th>RFC</th>
                    <th>Régimen fiscal</th>
                    <th>Contador asignado</th>
                    <th>Adjuntos directos</th>
                    <th>Semáforo documental</th>
                    <th>Estado interno</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {list.slice((current - 1) * 10, current * 10).map((c) => (
                    <tr key={c.id}>
                      <td>
                        <Link to={dossierLink(c)} className="company-cell">
                          <div className="company-avatar">{c.name.slice(0, 2).toUpperCase()}</div>
                          <div>
                            <strong>
                              {c.name} {c.is_demo && <Badge tone="blue">DEMO</Badge>}
                            </strong>
                            <small>
                              Persona {c.person_type} {c.location && '· ' + c.location}
                            </small>
                          </div>
                        </Link>
                      </td>
                      <td className="rfc">
                        {c.rfc}
                        {c.duplicate_rfc && <Badge tone="amber">RFC duplicado: revisar</Badge>}
                        {c.archived && <Badge tone="amber">Archivada</Badge>}
                        {csfIsStale(c) && <Badge tone="amber">Constancia de más de 3 meses</Badge>}
                      </td>
                      <td>{c.regime}</td>
                      <td>{responsibleName(c, state.responsibles)}</td>
                      <td title="Solo documentos asociados directamente; no mide integridad documental">
                        {state.document_counts[c.id] ?? 0}
                      </td>
                      <td>
                        {lights[c.id] ? (
                          <DocumentLights company={lights[c.id]} compact />
                        ) : (
                          <Badge>Sin información</Badge>
                        )}
                      </td>
                      <td>
                        <Badge tone={toneOf(statusOf(c, state, period, fiscal?.company_summaries[c.id]))}>
                          {statusOf(c, state, period, fiscal?.company_summaries[c.id])}
                        </Badge>
                      </td>
                      <td>
                        <Link className="icon-button" aria-label={'Abrir ' + c.name} to={dossierLink(c)}>
                          <Eye size={17} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title={all.length ? 'No se encontraron empresas' : 'Comienza con tu primera empresa'}>
              {all.length ? (
                'Ajusta los filtros de búsqueda.'
              ) : canRegister ? (
                <>
                  <span>Registra tu primer contribuyente o importa tu cartera con el botón Importar.</span>
                  <div className="actions centered">
                    <Link className="btn primary" to="/empresas/nueva">
                      <Plus size={16} />
                      Registrar empresa
                    </Link>
                    <Link className="btn" to={dashboardUrl('empresas', 'importar')}>
                      Importar cartera
                    </Link>
                  </div>
                </>
              ) : (
                'Aún no tienes empresas asignadas. Solicita acceso al administrador del despacho.'
              )}
            </Empty>
          )}
          <div className="table-footer">
            <span>{list.length} empresas · Estado basado en registros internos</span>
            <div className="pagination">
              <button disabled={current === 1} onClick={() => setPage(current - 1)}>
                ‹
              </button>
              <span>
                {current} / {pages}
              </span>
              <button disabled={current === pages} onClick={() => setPage(current + 1)}>
                ›
              </button>
            </div>
          </div>
        </section>
      )}
    </>
  );
}
