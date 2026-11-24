import { useState, useEffect, useCallback, useRef, lazy, Suspense, Component, type ReactNode } from 'react';
import { agentLabel, pairLocalAgent } from './agentPairing';
import { can, canAnywhere, canRegisterCompanies, type Action } from './permissions';
import { NavLink, Link, Routes, Route, useLocation, useParams, Navigate } from 'react-router-dom';
import {
  Home,
  Building2,
  CloudDownload,
  FolderTree,
  ReceiptText,
  Files,
  Settings,
  Search,
  ChevronRight,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  LogOut,
  Sun,
  Moon,
  Monitor,
  CheckCircle2,
  X,
  ListTodo,
  ArrowRight,
} from 'lucide-react';
import { UnsavedNavigation } from './navigationGuard';
import { updateArchiveWarnings } from './archiveWarnings';
import { api } from './api';
import { companiesSection } from './companyNavigation';
import { Badge, Logo, Heading, Field, Empty } from './components/ui';
import Login from './modules/Login';
import type { State, CurrentUser } from './types';
import { OriginalIcon, moduleIconNames } from './components/OriginalIcon';
// Route modules load on demand so the initial bundle only carries the shell, login and home.
const Companies = lazy(() => import('./modules/Companies'));
const CompanyForm = lazy(() => import('./modules/CompanyForm'));
const Dossier = lazy(() => import('./modules/Dossier'));
const TasksAndDeadlines = lazy(() => import('./modules/TasksAndDeadlines'));
const Receipts = lazy(() => import('./modules/Receipts'));
const Recopila = lazy(() => import('./modules/Recopila'));
const Organizador = lazy(() => import('./modules/Organizador'));
const Declara = lazy(() => import('./modules/Declara'));
const AgentAdmin = lazy(() => import('./modules/AgentAdmin'));
const AccountSecurity = lazy(() => import('./modules/AccountSecurity'));
const StorageConnector = lazy(() => import('./modules/StorageConnector'));
function ModuleLoading() {
  return (
    <div className="empty" role="status">
      <RefreshCw size={28} />
      <h2>Cargando módulo…</h2>
    </div>
  );
}
// A chunk can fail to load (network drop, or an update replaced the hashed files): offer a reload
// instead of leaving a blank workspace. Resets when the route changes.
class ModuleBoundary extends Component<{ children: ReactNode; route: string }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidUpdate(previous: { route: string }) {
    if (this.state.failed && previous.route !== this.props.route) this.setState({ failed: false });
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <Empty title="No se pudo cargar el módulo">
        <p>Revisa la conexión con el servidor o recarga la página para obtener la versión actual.</p>
        <button className="btn" onClick={() => window.location.reload()}>
          Recargar
        </button>
      </Empty>
    );
  }
}
// Rediseño v2: una sola lista en el orden del diseño (Inicio, Empresas, CFDI, Recopila, Declara, Recibos,
// Configuración); «Tareas y vencimientos» se conserva junto a Empresas. Los grupos sólo ordenan.
const nav = [
  {
    group: 'General',
    items: [
      { path: '/', title: 'Inicio', icon: Home },
      { path: '/empresas', title: 'Empresas', icon: Building2 },
      { path: '/tareas', title: 'Tareas y vencimientos', icon: ListTodo },
    ],
  },
  {
    group: 'Automatización',
    items: [
      { path: '/organizador-cfdi', title: 'CFDI', icon: FolderTree },
      { path: '/recopilador-cfdi', title: 'Recopila', icon: CloudDownload },
      { path: '/declara', title: 'Declara', icon: Files },
      { path: '/recibos', title: 'Recibos', icon: ReceiptText },
    ],
  },
  { group: 'Sistema', items: [{ path: '/configuracion', title: 'Configuración', icon: Settings }] },
];
const ROLE_NAMES: Record<CurrentUser['role'], string> = {
  admin: 'Administrador',
  contador: 'Contador',
  auxiliar: 'Auxiliar',
};
type Shared = { state: State; refresh: () => Promise<void>; notify: (m: string) => void };
function CompaniesRoute(props: Shared) {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  if (params.get('tab') === 'Calendario fiscal') {
    params.set('tab', 'calendario');
    return <Navigate to={'/tareas?' + params.toString()} replace />;
  }
  const target = companiesSection(params.get('tab'), params.get('vista'));
  if ('redirect' in target) return <Navigate to={target.redirect} replace />;
  return <Companies {...props} />;
}
function CompanyRoute({ editing = false, ...props }: Shared & { editing?: boolean }) {
  const { id } = useParams();
  const company = props.state.companies.find((c) => c.id === id);
  return !company ? (
    <Empty title="Empresa no encontrada">
      <Link to="/empresas">Volver al directorio</Link>
    </Empty>
  ) : editing && !can(props.state.current_user, 'empresa.editar', company.id) ? (
    <Navigate to={'/empresas/' + company.id} replace />
  ) : editing ? (
    <CompanyForm
      key={company.id}
      userId={props.state.current_user.id}
      admin={props.state.current_user.admin}
      responsible={props.state.responsibles?.find((r) => r.id === company.accountant_id)}
      ocrAvailable={props.state.integrations.ocr}
      company={company}
      onSaved={props.refresh}
      notify={props.notify}
    />
  ) : (
    <Dossier key={company.id} company={company} {...props} />
  );
}
/** Rediseño v2: accesos rápidos de la bienvenida. Descripciones de lo que cada módulo hace hoy; sólo se
 *  muestran los módulos que el usuario puede abrir (mismas acciones que el menú). */
const QUICK_ACCESS: {
  path: string;
  title: string;
  description: string;
  tone: string;
  icon?: typeof Building2;
  original?: keyof typeof moduleIconNames;
}[] = [
  {
    path: '/empresas',
    title: 'Empresas',
    description: 'Expedientes, vigencias documentales y obligaciones por periodo.',
    tone: 'indigo',
    icon: Building2,
  },
  {
    path: '/organizador-cfdi',
    title: 'CFDI',
    description: 'Organiza emitidos y recibidos y consulta el calendario de cada empresa.',
    tone: 'green',
    original: 'organizador-cfdi',
  },
  {
    path: '/recopilador-cfdi',
    title: 'Recopila',
    description: 'Relaciona pólizas con sus comprobantes y prepara sus PDF.',
    tone: 'blue',
    original: 'recopilador-cfdi',
  },
  {
    path: '/declara',
    title: 'Declara',
    description: 'Analiza declaraciones y acuses y lleva el control mensual.',
    tone: 'orange',
    original: 'declara',
  },
];
function Welcome({ name, identity }: { name: string; identity: CurrentUser | null }) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60000);
    return () => clearInterval(timer);
  }, []);
  const greeting = now.getHours() < 12 ? 'Buenos días' : now.getHours() < 19 ? 'Buenas tardes' : 'Buenas noches';
  const cards = QUICK_ACCESS.filter((c) => !MODULE_ACTIONS[c.path] || canAnywhere(identity, MODULE_ACTIONS[c.path]));
  return (
    <div className="welcome">
      <div className="welcome-brand">
        <Logo size={56} />
        <div>
          <strong>ContaSuite</strong>
          <small>Gestión contable inteligente</small>
        </div>
      </div>
      <h1>
        {greeting}
        {name ? ',' : ''}
      </h1>
      {name && <div className="welcome-name">{name}</div>}
      <p className="welcome-title">Bienvenido a ContaSuite</p>
      <small>Tu espacio de trabajo contable.</small>
      {cards.length > 0 && (
        <section className="quick-access" aria-label="Accesos rápidos">
          {cards.map((c) => {
            const Icon = c.icon;
            return (
              <Link key={c.path} to={c.path} className="quick-card">
                <span className={'quick-icon tone-' + c.tone} aria-hidden>
                  {c.original ? (
                    <OriginalIcon name={moduleIconNames[c.original]} size={26} />
                  ) : (
                    Icon && <Icon size={20} />
                  )}
                </span>
                <ArrowRight className="quick-arrow" size={18} aria-hidden />
                <strong>{c.title}</strong>
                <span>{c.description}</span>
              </Link>
            );
          })}
        </section>
      )}
    </div>
  );
}
// Automation modules open with their action in at least one company (Bloque 2).
const MODULE_ACTIONS: Record<string, Action> = {
  '/recopilador-cfdi': 'recopila.usar',
  '/organizador-cfdi': 'cfdi.usar',
  '/declara': 'declara.usar',
  '/recibos': 'recibos.usar',
};

/** Themes in the order the top-bar button cycles through them (Configuración › Apariencia lists the same three). */
const THEMES = [
  { id: 'light', name: 'Claro' },
  { id: 'dark', name: 'Oscuro' },
  { id: 'contrast', name: 'Alto contraste' },
];

export default function App() {
  const [token, setToken] = useState('');
  const [identity, setIdentity] = useState<CurrentUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [open, setOpen] = useState(false);
  // Panel lateral contraíble en escritorio (se recuerda por navegador).
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem('contasuite-sidebar-collapsed') === '1';
    } catch {
      return false;
    }
  });
  const toggleSidebar = () => {
    if (window.matchMedia('(max-width: 900px)').matches) {
      setOpen((o) => !o);
      return;
    }
    setCollapsed((c) => {
      try {
        localStorage.setItem('contasuite-sidebar-collapsed', c ? '0' : '1');
      } catch {
        /* sin almacenamiento */
      }
      return !c;
    });
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        toggleSidebar();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const [globalSearch, setGlobalSearch] = useState('');
  const [name, setName] = useState(localStorage.getItem('contasuite-name') || '');
  const [theme, setTheme] = useState(localStorage.getItem('contasuite-theme') || 'light');
  const themeName = (THEMES.find((t) => t.id === theme) || THEMES[0]).name;
  const location = useLocation();
  // Bloque 6 (C3): the toast stays mounted while it leaves, then the message is cleared.
  const [leaving, setLeaving] = useState(false);
  const leaveTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const notify = useCallback((m: string) => {
    clearTimeout(leaveTimer.current);
    setLeaving(false);
    setMessage(m);
  }, []);
  const dismiss = useCallback(() => {
    setLeaving(true);
    clearTimeout(leaveTimer.current);
    leaveTimer.current = setTimeout(() => {
      setMessage('');
      setLeaving(false);
    }, 220);
  }, []);
  const refresh = useCallback(async () => {
    const s = await api<State>('/state');
    updateArchiveWarnings(s.companies);
    setState(s);
    setIdentity(s.current_user);
    setError('');
  }, []);
  useEffect(() => {
    if (!token) return;
    refresh().catch((e) => setError(e.message));
    // Background poll once a minute; data changes made in this tab refresh immediately via
    // contasuite-data-changed, and returning to the tab refreshes too.
    const timer = setInterval(() => refresh().catch((e) => setError(e.message)), 60000);
    const visible = () => {
      if (document.visibilityState === 'visible') void refresh().catch((e) => setError(e.message));
    };
    document.addEventListener('visibilitychange', visible);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [token, refresh]);
  // Bloque 4: pair the agent of this computer with the signed-in user (silently; no agent is normal).
  const [localAgent, setLocalAgent] = useState('');
  const linkState = state?.agent_link?.state;
  const displayName = state?.current_user.display_name || '';
  useEffect(() => {
    if (!token || !linkState || linkState === 'online' || state?.current_user.bootstrap) return;
    let alive = true;
    void pairLocalAgent(state?.agent_link, displayName).then((result) => {
      if (!alive) return;
      setLocalAgent(result);
      if (result === 'paired') setTimeout(() => void refresh().catch(() => undefined), 6000);
    });
    return () => {
      alive = false;
    };
    // Re-evaluated when the link state changes, not on every refresh of the same state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, linkState, displayName]);
  useEffect(() => {
    const changed = () => {
      if (token) void refresh().catch((e) => setError(e.message));
    };
    window.addEventListener('contasuite-data-changed', changed);
    return () => window.removeEventListener('contasuite-data-changed', changed);
  }, [token, refresh]);
  useEffect(() => {
    if (message) {
      const timer = setTimeout(dismiss, 6500);
      return () => clearTimeout(timer);
    }
  }, [message, dismiss]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('contasuite-theme', theme);
    const favicon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (favicon) favicon.href = '/icons/original/' + (theme === 'light' ? 'claro' : 'oscuro') + '/64/CS_ContaSuite.png';
  }, [theme]);
  useEffect(() => {
    setOpen(false);
    setGlobalSearch('');
  }, [location.pathname]);
  const ended = useCallback(() => {
    updateArchiveWarnings([]);
    sessionStorage.removeItem('contasuite-token');
    setToken('');
    setState(null);
    setIdentity(null);
    setError('');
  }, []);
  async function authenticated() {
    const me = await api<CurrentUser>('/auth/me');
    if (me.bootstrap) {
      ended();
      return;
    }
    setIdentity(me);
    setName(localStorage.getItem('contasuite-name:' + me.id) || me.display_name);
    setToken('session');
    await refresh();
  }
  useEffect(() => {
    let alive = true;
    api<CurrentUser>('/auth/me')
      .then((me) => {
        if (alive && !me.bootstrap) {
          sessionStorage.removeItem('contasuite-token');
          setIdentity(me);
          setName(localStorage.getItem('contasuite-name:' + me.id) || me.display_name);
          setToken('session');
        }
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setAuthLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    window.addEventListener('contasuite-session-expired', ended);
    return () => window.removeEventListener('contasuite-session-expired', ended);
  }, [ended]);
  async function logout() {
    try {
      await api('/auth/logout', 'POST');
      ended();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (authLoading)
    return (
      <div className="login-page">
        <p role="status">Consultando sesión…</p>
      </div>
    );
  if (!token) return <Login onAuthenticated={authenticated} />;
  const active = nav.flatMap((g) => g.items).find((i) => i.path !== '/' && location.pathname.startsWith(i.path));
  const shared = state ? { state, refresh, notify } : null;
  const agentOnline = state?.agent_link?.state === 'online';
  return (
    <div className={'app-shell' + (collapsed ? ' sidebar-collapsed' : '')}>
      <a className="skip-link" href="#main-content">
        Saltar al contenido
      </a>
      <aside className={'sidebar ' + (open ? 'open' : '')}>
        <div className="sidebar-head">
          <Link to="/" className="brand">
            <Logo sidebar />
            <div>
              <strong>ContaSuite</strong>
              <small>Gestión contable inteligente</small>
            </div>
          </Link>
          <button
            className="icon-button sidebar-toggle"
            onClick={toggleSidebar}
            aria-label={collapsed ? 'Fijar panel lateral expandido' : 'Contraer panel lateral'}
            aria-expanded={!collapsed}
            title={(collapsed ? 'Expandir' : 'Contraer') + ' panel (Ctrl+B)'}
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>
        <nav>
          {nav.map((g) => (
            <div key={g.group}>
              {g.items
                .filter((i) => !MODULE_ACTIONS[i.path] || canAnywhere(identity, MODULE_ACTIONS[i.path]))
                .map((i) => (
                  <NavLink
                    key={i.path}
                    to={i.path}
                    end={i.path === '/'}
                    title={collapsed ? i.title : undefined}
                    aria-label={i.title}
                  >
                    {moduleIconNames[i.path.slice(1)] ? (
                      <OriginalIcon name={moduleIconNames[i.path.slice(1)]} size={24} />
                    ) : (
                      <i.icon size={18} strokeWidth={1.6} />
                    )}
                    <span>{i.title}</span>
                  </NavLink>
                ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="profile-avatar">
            {name
              ? name
                  .split(' ')
                  .slice(0, 2)
                  .map((w) => w[0])
                  .join('')
              : 'CS'}
          </div>
          <div>
            <strong>{name || 'Mi despacho'}</strong>
            <small title="ContaSuite v1.0 RC1">
              {identity ? ROLE_NAMES[identity.role] || 'Usuario' : 'ContaSuite'}
            </small>
          </div>
          <button className="icon-button" onClick={logout} aria-label="Cerrar sesión">
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      {open && <button className="sidebar-shade" aria-label="Cerrar menú" onClick={() => setOpen(false)} />}
      <header className="topbar">
        <button className="icon-button menu-button" onClick={toggleSidebar} aria-label="Abrir menú" title="Abrir menú">
          <Menu size={21} />
        </button>
        <div className="breadcrumbs">
          <Link to="/">ContaSuite</Link>
          <ChevronRight size={13} />
          <span>Workspace Fiscal</span>
          {active && (
            <>
              <ChevronRight size={13} />
              <span className="current">{active.title}</span>
            </>
          )}
        </div>
        <div className="global-search">
          <Search size={16} />
          <input
            value={globalSearch}
            onChange={(e) => setGlobalSearch(e.target.value)}
            placeholder="Buscar empresa, RFC…"
            aria-label="Búsqueda global"
          />
          {globalSearch && (
            <div className="search-results">
              {state?.companies
                .filter(
                  (c) =>
                    c.archived !== true && (c.name + ' ' + c.rfc).toLowerCase().includes(globalSearch.toLowerCase()),
                )
                .slice(0, 8)
                .map((c) => (
                  <Link key={c.id} to={'/empresas/' + c.id}>
                    {c.name}
                    <small>{c.rfc}</small>
                  </Link>
                ))}
              {!state?.companies.some(
                (c) => c.archived !== true && (c.name + ' ' + c.rfc).toLowerCase().includes(globalSearch.toLowerCase()),
              ) && <p>Sin coincidencias</p>}
            </div>
          )}
        </div>
        <div className="system-indicator">
          <span className={'dot ' + (agentOnline ? 'green' : 'neutral')} />
          <span>{agentLabel(state?.agent_link, localAgent)}</span>
        </div>
        <button
          className="icon-button"
          onClick={() =>
            refresh()
              .then(() => notify('Datos actualizados'))
              .catch((e) => notify(e.message))
          }
          aria-label="Actualizar datos"
        >
          <RefreshCw size={17} />
        </button>
        <button
          className="theme-button"
          aria-label={'Cambiar tema (actual: ' + themeName + ')'}
          title={'Tema: ' + themeName + '. Pulsa para cambiar.'}
          onClick={() => setTheme(THEMES[(THEMES.findIndex((t) => t.id === theme) + 1) % THEMES.length].id)}
        >
          {theme === 'dark' ? (
            <Moon size={17} aria-hidden />
          ) : theme === 'contrast' ? (
            <Monitor size={17} aria-hidden />
          ) : (
            <Sun size={17} aria-hidden />
          )}
          <span>{themeName}</span>
        </button>
        <div className="profile-avatar small">{name ? name[0] : 'CS'}</div>
      </header>
      <UnsavedNavigation />
      <main
        id="main-content"
        tabIndex={-1}
        className={'workspace ' + (location.pathname === '/' ? 'home-workspace' : '')}
      >
        {error && (
          <div className="error-banner" role="alert">
            No se pudo actualizar: {error}{' '}
            <button onClick={() => refresh().catch((e) => setError(e.message))}>Reintentar</button>
            <button onClick={logout}>Cerrar sesión</button>
          </div>
        )}
        {shared ? (
          <ModuleBoundary route={location.pathname}>
            <Suspense fallback={<ModuleLoading />}>
              <Routes>
                <Route path="/" element={<Welcome name={name} identity={identity} />} />
                <Route path="/empresas" element={<CompaniesRoute {...shared} />} />
                <Route
                  path="/empresas/nueva"
                  element={
                    canRegisterCompanies(identity) ? (
                      <CompanyForm
                        userId={identity?.id}
                        admin={!!identity?.admin}
                        ocrAvailable={!!state?.integrations.ocr}
                        onSaved={refresh}
                        notify={notify}
                      />
                    ) : (
                      <Navigate to="/empresas" replace />
                    )
                  }
                />
                <Route
                  path="/empresas/:id/editar"
                  element={
                    canRegisterCompanies(identity) || canAnywhere(identity, 'empresa.editar') ? (
                      <CompanyRoute {...shared} editing />
                    ) : (
                      <Navigate to="/empresas" replace />
                    )
                  }
                />
                <Route path="/empresas/:id" element={<CompanyRoute {...shared} />} />
                <Route path="/tareas" element={<TasksAndDeadlines {...shared} />} />
                <Route
                  path="/recopilador-cfdi"
                  element={
                    canAnywhere(identity, MODULE_ACTIONS['/recopilador-cfdi']) ? (
                      <Recopila {...shared} />
                    ) : (
                      <Navigate to="/empresas" replace />
                    )
                  }
                />
                <Route
                  path="/recibos"
                  element={
                    canAnywhere(identity, MODULE_ACTIONS['/recibos']) ? (
                      <Receipts {...shared} />
                    ) : (
                      <Navigate to="/empresas" replace />
                    )
                  }
                />
                <Route
                  path="/organizador-cfdi"
                  element={
                    canAnywhere(identity, MODULE_ACTIONS['/organizador-cfdi']) ? (
                      <Organizador {...shared} />
                    ) : (
                      <Navigate to="/empresas" replace />
                    )
                  }
                />
                <Route
                  path="/declara"
                  element={
                    canAnywhere(identity, MODULE_ACTIONS['/declara']) ? (
                      <Declara {...shared} />
                    ) : (
                      <Navigate to="/empresas" replace />
                    )
                  }
                />
                <Route
                  path="/configuracion"
                  element={
                    <>
                      <Heading
                        title="Configuración del sistema"
                        description="Preferencias del espacio de trabajo y estado real de las integraciones."
                      />
                      <div className="settings-grid">
                        <section className="card padded">
                          <h2>Preferencias del despacho</h2>
                          <Field label="Nombre mostrado en el inicio">
                            <input
                              value={name}
                              onChange={(e) => {
                                setName(e.target.value);
                                localStorage.setItem('contasuite-name:' + identity?.id, e.target.value);
                              }}
                              placeholder="C.P. Jesús Alejandro"
                            />
                          </Field>
                          <h3>Apariencia</h3>
                          <div className="theme-options">
                            {[
                              ['light', 'Claro', Sun],
                              ['dark', 'Oscuro', Moon],
                              ['contrast', 'Alto contraste', Monitor],
                            ].map(([v, t, I]) => {
                              const Icon = I as typeof Sun;
                              return (
                                <button
                                  key={String(v)}
                                  className={'btn ' + (theme === v ? 'selected' : '')}
                                  onClick={() => setTheme(String(v))}
                                >
                                  <Icon size={18} />
                                  {String(t)}
                                </button>
                              );
                            })}
                          </div>
                          <small className="muted">Estas preferencias se guardan en este navegador.</small>
                        </section>
                        <section className="card padded">
                          <h2>Estado de servicios</h2>
                          <dl>
                            <div>
                              <dt>Base de datos</dt>
                              <dd>{state?.database}</dd>
                            </div>
                            <div>
                              <dt>API FastAPI</dt>
                              <dd>
                                <Badge tone="green">Conectada</Badge>
                              </dd>
                            </div>
                            <div>
                              <dt>Consulta SAT</dt>
                              <dd>
                                <Badge>Pendiente de integrar</Badge>
                              </dd>
                            </div>
                            <div>
                              <dt>OCR</dt>
                              <dd>
                                {state?.integrations.ocr ? (
                                  <Badge tone="green">Local: constancias escaneadas</Badge>
                                ) : (
                                  <Badge>No instalado</Badge>
                                )}
                              </dd>
                            </div>
                          </dl>
                          <h3 id="agentes">Agentes locales</h3>
                          {identity?.admin && !identity.bootstrap ? (
                            <AgentAdmin notify={notify} />
                          ) : (
                            <p className="muted">
                              {agentLabel(state?.agent_link, localAgent)}. El agente de tu equipo se vincula al iniciar
                              sesión; analiza sólo carpetas autorizadas de tus empresas.
                            </p>
                          )}
                        </section>
                      </div>
                      {identity?.admin && !identity.bootstrap && <StorageConnector notify={notify} />}
                      {identity && !identity.bootstrap && (
                        <AccountSecurity
                          identity={identity}
                          companies={state?.companies || []}
                          notify={notify}
                          onEnded={ended}
                        />
                      )}
                    </>
                  }
                />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </ModuleBoundary>
        ) : (
          <div className="empty">
            <RefreshCw size={28} />
            <h2>Conectando con ContaSuite…</h2>
          </div>
        )}
      </main>
      {message && (
        <div className="toast" role="status" data-leaving={leaving || undefined}>
          <CheckCircle2 size={18} />
          <span>{message}</span>
          <button aria-label="Cerrar mensaje" onClick={dismiss}>
            <X size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
