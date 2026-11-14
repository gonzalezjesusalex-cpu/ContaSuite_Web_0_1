import { useState, useEffect } from 'react';
import { canRegisterCompanies, csfIsStale, responsibleName } from '../permissions';
import { Link, useSearchParams } from 'react-router-dom';
import { Plus, Eye, Search, Download, CalendarDays, FolderOpen } from 'lucide-react';
import { api, csv, today } from '../api';
import { Badge, Empty, Heading } from '../components/ui';
import Documents from './Documents';
import IntegralDashboard from './IntegralDashboard';
import CompanyImporter from './CompanyImporter';
import Credentials, { AlertCenter } from './Credentials';
import FiscalControl from './FiscalControl';
import { useFiscalRead, fiscalStatus, exportFiscal, type Summary } from './fiscalRead';
import { confirmDiscard } from '../navigationGuard';
import { companiesSection, companiesSections, companiesUrl, companiesViews } from '../companyNavigation';
import type { State, Company } from '../types';
export const statusOf = (_c: Company, _state: State, _period?: string, summary?: Summary) => fiscalStatus(summary);
export const toneOf = (s: string) => (s === 'Crítico' ? 'red' : s === 'Sin pendientes' ? 'green' : 'amber');
// The tasks redirect is resolved by the route before this page renders.
const target = (tab: string | null, vista: string | null) => {
  const t = companiesSection(tab, vista);
  return 'section' in t ? t : { section: 'Panel', view: 'General' };
};
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
  const [tab, setTab] = useState(() => target(params.get('tab'), params.get('vista')).section);
  const [vista, setVista] = useState(() => target(params.get('tab'), params.get('vista')).view);
  useEffect(() => {
    const t = target(params.get('tab'), params.get('vista'));
    setTab(t.section);
    setVista(t.view);
  }, [params]);
  const [period, setPeriod] = useState(
    /^20\d{2}-(0[1-9]|1[0-2])$/.test(params.get('period') || '') ? params.get('period')! : today().slice(0, 7),
  );
  const [query, setQuery] = useState(params.get('query') || '');
  // Responsible by user (Bloque 2): '' all, 'mine', 'none' (no linked user) or a user id.
  const [responsible, setResponsible] = useState(params.get('responsible') || '');
  const [status, setStatus] = useState(params.get('status') || '');
  const [page, setPage] = useState(1);
  const { data: fiscal, error: fiscalError } = useFiscalRead(
    period,
    undefined,
    (params.get('archive') || 'active') !== 'active',
  );
  const [archive, setArchive] = useState(params.get('archive') || 'active'),
    [sort, setSort] = useState(params.get('sort') || 'name');
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
  useEffect(() => {
    setParams(
      (previous) => {
        const q = new URLSearchParams(previous);
        for (const [key, value] of Object.entries({ tab, period, query, responsible, status, archive, sort }))
          q.set(key, value);
        if (vista) q.set('vista', vista);
        else q.delete('vista');
        return q;
      },
      { replace: true },
    );
    // setParams changes identity on every URL change (React Router 7); as a dependency this URL sync
    // would re-run after its own write. It only has to follow the page state below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, vista, period, query, responsible, status, archive, sort]);
  const all = directory;
  const list = all.filter((c) => !status || statusOf(c, state, period, fiscal?.company_summaries[c.id]) === status);
  const pages = Math.max(1, Math.ceil(list.length / 10));
  const current = Math.min(page, pages);
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
  return (
    <>
      <Heading
        eyebrow="DESPACHO FISCAL DIGITAL · CONTROL DEL DESPACHO"
        title="Centro de Control Fiscal"
        description="Supervisa el expediente, las obligaciones y el trabajo de tus empresas clientes."
        actions={
          <>
            <label className="period-control">
              <CalendarDays size={17} />
              <span>
                <small>PERIODO ACTIVO</small>
                <input
                  aria-label="Periodo activo"
                  type="month"
                  value={period}
                  onChange={(e) => {
                    if (confirmDiscard()) setPeriod(e.target.value);
                  }}
                />
              </span>
            </label>
            <Link className="btn" to={companiesUrl('Documentos', 'Expedientes por empresa')}>
              <FolderOpen size={16} />
              Expedientes
            </Link>
            {canRegisterCompanies(state.current_user) && (
              <Link className="btn primary" to="/empresas/nueva">
                <Plus size={17} />
                Registrar empresa
              </Link>
            )}
          </>
        }
      />
      <div className="tabs card" role="group" aria-label="Secciones de Empresas">
        {companiesSections.map((t) => (
          <button
            className={t === tab ? 'active' : ''}
            aria-pressed={t === tab}
            key={t}
            onClick={() => {
              if (!confirmDiscard()) return;
              setTab(t);
              setVista(companiesViews[t]?.[0] || '');
              setParams({ tab: t, period });
            }}
          >
            {t}
            {t === 'Directorio' && <span>{all.length}</span>}
          </button>
        ))}
      </div>
      {companiesViews[tab] && (
        <div className="tabs card subtabs" role="group" aria-label={'Vista de ' + tab}>
          {companiesViews[tab].map((v) => (
            <button
              className={v === vista ? 'active' : ''}
              aria-pressed={v === vista}
              key={v}
              onClick={() => {
                if (confirmDiscard()) setVista(v);
              }}
            >
              {v}
            </button>
          ))}
        </div>
      )}
      {tab === 'Panel' ? (
        <IntegralDashboard state={state} period={period} view={vista === 'General' ? 'Dashboard general' : vista} />
      ) : tab === 'Importar' ? (
        <CompanyImporter state={state} />
      ) : tab === 'Credenciales' ? (
        vista === 'Centro de alertas' ? (
          <AlertCenter state={state} />
        ) : (
          <Credentials state={state} />
        )
      ) : tab === 'Obligaciones' ? (
        <>
          <div className="actions section-actions">
            <button className="btn" disabled={!fiscal} onClick={() => fiscal && exportFiscal(fiscal, period)}>
              <Download size={16} />
              Obligaciones del periodo CSV
            </button>
          </div>
          <FiscalControl state={state} period={period} notify={notify} />
        </>
      ) : tab === 'Documentos' && vista === 'Expedientes por empresa' ? (
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
      ) : tab === 'Documentos' ? (
        <Documents notify={notify} refresh={refresh} />
      ) : (
        <>
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
                  placeholder="Buscar empresa, RFC o nombre comercial…"
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
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Empresa / Razón social</th>
                      <th>RFC</th>
                      <th>Régimen fiscal</th>
                      <th>Contador asignado</th>
                      <th>Adjuntos directos</th>
                      <th>Opinión 32-D</th>
                      <th>Estado interno</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.slice((current - 1) * 10, current * 10).map((c) => (
                      <tr key={c.id}>
                        <td>
                          <Link
                            to={
                              '/empresas/' +
                              c.id +
                              '?' +
                              new URLSearchParams({ period, query, responsible, status, archive, sort })
                            }
                            className="company-cell"
                          >
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
                          <Badge>Sin consultar</Badge>
                        </td>
                        <td>
                          <Badge tone={toneOf(statusOf(c, state, period, fiscal?.company_summaries[c.id]))}>
                            {statusOf(c, state, period, fiscal?.company_summaries[c.id])}
                          </Badge>
                        </td>
                        <td>
                          <Link
                            className="icon-button"
                            aria-label={'Abrir ' + c.name}
                            to={
                              '/empresas/' +
                              c.id +
                              '?' +
                              new URLSearchParams({ period, query, responsible, status, archive, sort })
                            }
                          >
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
                ) : canRegisterCompanies(state.current_user) ? (
                  <>
                    <span>Registra tu primer contribuyente o importa tu cartera desde Empresas › Importar.</span>
                    <div className="actions centered">
                      <Link className="btn primary" to="/empresas/nueva">
                        <Plus size={16} />
                        Registrar empresa
                      </Link>
                      <Link className="btn" to={companiesUrl('Importar')}>
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
        </>
      )}
    </>
  );
}
