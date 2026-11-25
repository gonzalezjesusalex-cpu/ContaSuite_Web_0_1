import { lazy, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, Navigate, NavLink, useNavigate, useParams } from 'react-router-dom';
import { ChevronRight, KeyRound, Monitor, Moon, Sun } from 'lucide-react';
import { agentLabel } from '../agentPairing';
import { Badge, Field, Heading } from '../components/ui';
import { markFormSaved } from '../dirtyForms';
import { SETTINGS_SECTIONS, settingsSection } from '../settingsSections';
import type { CurrentUser, State } from '../types';
const AgentAdmin = lazy(() => import('./AgentAdmin'));
const AccountSecurity = lazy(() => import('./AccountSecurity'));
const StorageConnector = lazy(() => import('./StorageConnector'));

type Props = {
  state: State;
  identity: CurrentUser | null;
  name: string;
  onNameSaved: (name: string) => void;
  theme: string;
  setTheme: (theme: string) => void;
  localAgent: string;
  notify: (m: string) => void;
  onEnded: () => void;
};

/** Configuración por pestañas: el menú lleva a /configuracion/<sección> y sólo se monta la sección activa,
 *  así cada una pide sus datos al abrirse (Auditoría y Almacenamiento incluidas). */
export default function Settings(props: Props) {
  const { section: slug } = useParams();
  const navigate = useNavigate();
  const { identity } = props;
  const current = settingsSection(slug, identity);
  const content = useRef<HTMLDivElement>(null);
  const first = useRef(true);
  useEffect(() => {
    if (!current) return;
    // La primera carga deja el foco donde lo pone la navegación general; los cambios de sección llevan el
    // panel arriba y el foco al título de la sección.
    if (first.current) {
      first.current = false;
      return;
    }
    window.scrollTo({ top: 0 });
    const heading = content.current?.querySelector<HTMLElement>('h2');
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
  }, [current]);
  if (!current) return <Navigate to="/configuracion/perfil" replace />;
  const sections = SETTINGS_SECTIONS.filter((s) => s.shown(identity));
  return (
    <>
      <Heading
        title="Configuración"
        description="Preferencias del despacho, tema, servicios, cuenta, permisos y auditoría."
      />
      <div className="v2-settings">
        <nav className="v2-settings-nav" aria-label="Secciones de Configuración">
          {sections.map(({ slug: id, label, icon: Icon }) => (
            <NavLink key={id} to={'/configuracion/' + id}>
              <Icon size={17} aria-hidden />
              {label}
            </NavLink>
          ))}
          <Link to="/empresas?tab=Credenciales" className="v2-settings-external">
            <KeyRound size={17} aria-hidden />
            Gestor de contraseñas
            <ChevronRight size={15} aria-hidden className="v2-settings-out" />
          </Link>
        </nav>
        <div className="v2-settings-picker">
          <Field label="Sección de Configuración">
            <select value={current.slug} onChange={(e) => navigate('/configuracion/' + e.target.value)}>
              {sections.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {s.label}
                </option>
              ))}
            </select>
          </Field>
          <Link to="/empresas?tab=Credenciales" className="v2-settings-external">
            <KeyRound size={17} aria-hidden />
            Gestor de contraseñas
            <ChevronRight size={15} aria-hidden className="v2-settings-out" />
          </Link>
        </div>
        <div className="v2-settings-content" ref={content}>
          <Section {...props} slug={current.slug} />
        </div>
      </div>
    </>
  );
}

function Section({ slug, state, identity, notify, onEnded, ...props }: Props & { slug: string }) {
  if (slug === 'perfil')
    return <Profile key={props.name} name={props.name} onSaved={props.onNameSaved} notify={notify} />;
  if (slug === 'tema')
    return (
      <section id="cfg-tema" className="card padded">
        <h2>Tema y accesibilidad</h2>
        <p className="muted">Claro, oscuro o alto contraste. Las animaciones se reducen cuando el sistema lo pide.</p>
        <div className="theme-options">
          {(
            [
              ['light', 'Claro', Sun],
              ['dark', 'Oscuro', Moon],
              ['contrast', 'Alto contraste', Monitor],
            ] as const
          ).map(([v, t, Icon]) => (
            <button
              key={v}
              className={'btn ' + (props.theme === v ? 'selected' : '')}
              aria-pressed={props.theme === v}
              onClick={() => props.setTheme(v)}
            >
              <Icon size={18} />
              {t}
            </button>
          ))}
        </div>
        <small className="muted">Estas preferencias se guardan en este navegador.</small>
      </section>
    );
  if (slug === 'servicios')
    return (
      <section id="cfg-servicios" className="card padded">
        <h2>Servicios y agentes</h2>
        <dl>
          <div>
            <dt>Base de datos</dt>
            <dd>{state.database}</dd>
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
              {state.integrations.ocr ? (
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
            {agentLabel(state.agent_link, props.localAgent)}. El agente de tu equipo se vincula al iniciar sesión;
            analiza sólo carpetas autorizadas de tus empresas.
          </p>
        )}
      </section>
    );
  if (slug === 'almacenamiento') return <StorageConnector notify={notify} />;
  if (!identity) return null;
  return (
    <AccountSecurity
      section={slug as 'seguridad' | 'equipo' | 'auditoria'}
      identity={identity}
      companies={state.companies}
      notify={notify}
      onEnded={onEnded}
    />
  );
}

/** Perfil se guarda con su botón: mientras el nombre cambiado no se guarde, la guarda general de cambios sin
 *  guardar (formularios) avisa al cambiar de sección o salir. */
function Profile({
  name,
  onSaved,
  notify,
}: {
  name: string;
  onSaved: (n: string) => void;
  notify: (m: string) => void;
}) {
  const [draft, setDraft] = useState(name);
  function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const value = draft.trim();
    onSaved(value);
    markFormSaved(e.currentTarget);
    notify('Perfil guardado');
  }
  return (
    <section id="cfg-perfil" className="card padded">
      <h2>Perfil</h2>
      <p className="muted">Nombre que aparece en la pantalla de inicio de este navegador.</p>
      <form className="v2-settings-form" onSubmit={save}>
        <Field label="Nombre mostrado en el inicio">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            maxLength={80}
            placeholder="C.P. Jesús Alejandro"
          />
        </Field>
        <div className="actions">
          <button className="btn primary" disabled={draft.trim() === name}>
            Guardar
          </button>
        </div>
      </form>
    </section>
  );
}
