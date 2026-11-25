import { useEffect, useState, type FormEvent } from 'react';
import { api, dateLabel } from '../api';
import { Field, Modal } from '../components/ui';
import { stitchButton, stitchPrimary, stitchCard } from '../components/stitch';
import type { Company, CurrentUser } from '../types';
import { can, canManageUsers, ROLE_LABELS, type Action } from '../permissions';
import ResponsibleReconciliation from './ResponsibleReconciliation';

// `actions`: an auxiliary's explicit actions, sent back unchanged; a changed access drops them and the
// server applies the default for that access.
type Grant = { company_id: string; access: string; actions?: string[] | null };
type Account = {
  id: string;
  username: string;
  display_name: string;
  admin: boolean;
  role: 'admin' | 'contador' | 'auxiliar';
  enabled: boolean;
  revision: number;
  grants: Grant[];
};
type Event = {
  id: string;
  actor_id: string;
  action: string;
  outcome: string;
  code: string | null;
  created_at: string;
  document_id: string | null;
};
export default function AccountSecurity({
  identity,
  companies,
  notify,
  onEnded,
}: {
  identity: CurrentUser;
  companies: Company[];
  notify: (m: string) => void;
  onEnded: () => void;
}) {
  const [users, setUsers] = useState<Account[]>([]);
  const [edit, setEdit] = useState<Account | 'new' | null>(null);
  const [reload, setReload] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [kind, setKind] = useState('security');
  const [page, setPage] = useState(0);
  const [events, setEvents] = useState<{ items: Event[]; total: number } | null>(null);
  const manager = canManageUsers(identity);
  useEffect(() => {
    if (!manager) return;
    const c = new AbortController();
    api<Account[]>('/auth/users', 'GET', undefined, c.signal)
      .then(setUsers)
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      });
    return () => c.abort();
  }, [manager, reload]);
  useEffect(() => {
    if (!identity.admin) return;
    const c = new AbortController();
    setEvents(null);
    api<{ items: Event[]; total: number }>(
      '/auth/audit?kind=' + kind + '&offset=' + page * 50,
      'GET',
      undefined,
      c.signal,
    )
      .then(setEvents)
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      });
    return () => c.abort();
  }, [identity.admin, reload, kind, page]);
  async function change(e: FormEvent) {
    e.preventDefault();
    setError('');
    if (password !== confirm) {
      setError('Las contraseñas nuevas no coinciden.');
      return;
    }
    setBusy(true);
    try {
      await api('/auth/password', 'POST', { current_password: current, new_password: password });
      setCurrent('');
      setPassword('');
      setConfirm('');
      notify('Contraseña actualizada. Inicia sesión de nuevo.');
      onEnded();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id?: string) {
    setBusy(true);
    setError('');
    try {
      await api(id ? '/auth/users/' + id + '/revoke' : '/auth/logout-all', 'POST');
      notify('Sesiones revocadas.');
      if (!id || id === identity.id) onEnded();
      else setReload((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="account-security stitch-live-module">
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      <section id="cfg-cuenta" className={stitchCard + ' padded'}>
        <h2>Mi cuenta</h2>
        <p className="muted">
          {identity.display_name} · {ROLE_LABELS[identity.role] || 'Colaborador'}
        </p>
        <form className="account-password" onSubmit={change}>
          <Field label="Contraseña actual">
            <input
              required
              type="password"
              maxLength={128}
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </Field>
          <Field label="Nueva contraseña">
            <input
              required
              type="password"
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Field label="Repetir nueva contraseña">
            <input
              required
              type="password"
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </Field>
          <button className={stitchPrimary} disabled={busy}>
            Cambiar contraseña
          </button>
        </form>
        <button className={stitchButton} disabled={busy} onClick={() => revoke()}>
          Cerrar todas mis sesiones
        </button>
        <small className="muted">Cambiar la contraseña cierra las sesiones abiertas de esta cuenta.</small>
      </section>
      {manager && (
        <>
          <section id="cfg-equipo" className={stitchCard + ' padded'}>
            <div className="documents-header">
              <h2>{identity.admin ? 'Usuarios y permisos' : 'Auxiliares de mis empresas'}</h2>
              <button className={stitchPrimary} onClick={() => setEdit('new')}>
                {identity.admin ? 'Crear usuario' : 'Crear auxiliar'}
              </button>
            </div>
            <p className="muted">
              {identity.admin
                ? 'El administrador gestiona contadores y auxiliares. El contador opera sus empresas y crea auxiliares en ellas; el auxiliar consulta y realiza sólo las acciones que se le conceden.'
                : 'Gestiona los auxiliares de tus empresas. No puedes concederles acciones que tú no tienes; si un auxiliar trabaja también en empresas ajenas, sólo la administración cambia su nombre, estado o contraseña.'}
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Usuario</th>
                    <th>Perfil</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>
                        {u.display_name}
                        <small>{u.username}</small>
                      </td>
                      <td>
                        {ROLE_LABELS[u.role]}
                        {u.role !== 'admin' && <small>{u.grants.length} empresas asignadas</small>}
                      </td>
                      <td>{u.enabled ? 'Activo' : 'Desactivado'}</td>
                      <td>
                        <div className="actions">
                          <button className={stitchButton} onClick={() => setEdit(u)}>
                            Editar {u.username}
                          </button>
                          <button className={stitchButton} disabled={busy} onClick={() => revoke(u.id)}>
                            Revocar sesiones de {u.username}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
      {identity.admin && <ResponsibleReconciliation notify={notify} />}
      {identity.admin && (
        <>
          <section id="cfg-auditoria" className={stitchCard + ' padded'}>
            <div className="documents-header">
              <h2>Auditoría de accesos y operaciones</h2>
              <button className={stitchButton} onClick={() => setReload((v) => v + 1)}>
                Actualizar auditoría
              </button>
            </div>
            <Field label="Registro de auditoría">
              <select
                aria-label="Registro de auditoría"
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value);
                  setPage(0);
                }}
              >
                <option value="security">Sesiones y solicitudes</option>
                <option value="storage">Operaciones documentales</option>
              </select>
            </Field>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Responsable</th>
                    <th>Operación</th>
                    <th>Resultado</th>
                  </tr>
                </thead>
                <tbody>
                  {events?.items.map((e) => (
                    <tr key={e.id}>
                      <td>
                        {dateLabel(e.created_at)}
                        <small>{new Date(e.created_at).toLocaleTimeString('es-MX')}</small>
                      </td>
                      <td>{users.find((u) => u.id === e.actor_id)?.display_name || e.actor_id}</td>
                      <td>
                        {e.action}
                        {e.document_id && <small>Documento: {e.document_id}</small>}
                      </td>
                      <td>
                        {e.outcome}
                        {e.code && <small>{e.code}</small>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!events && <p role="status">Consultando auditoría…</p>}
            </div>
            <div className="recopila-pagination">
              <button className={stitchButton} disabled={page === 0 || !events} onClick={() => setPage((v) => v - 1)}>
                Anterior
              </button>
              <span>
                {events?.total ?? '…'} eventos · Página {page + 1}
              </span>
              <button
                className={stitchButton}
                disabled={!events || (page + 1) * 50 >= events.total}
                onClick={() => setPage((v) => v + 1)}
              >
                Siguiente
              </button>
            </div>
          </section>
        </>
      )}
      {edit && (
        <Editor
          account={edit === 'new' ? undefined : edit}
          companies={companies}
          identity={identity}
          onClose={() => setEdit(null)}
          onSaved={() => {
            setEdit(null);
            setReload((v) => v + 1);
            notify('Cuenta guardada. Sus sesiones anteriores se revocaron.');
          }}
        />
      )}
    </div>
  );
}

type Catalog = {
  read: string[];
  actions: { id: string; label: string }[];
  templates: { id: string; label: string; actions: string[] }[];
};
type Role = Account['role'];

const sameActions = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));

/** Per-company access of an auxiliary: a template or a custom choice of actions (catalog from the server). */
function AuxiliaryGrant({
  company,
  grant,
  catalog,
  allowed,
  disabled,
  onChange,
}: {
  company: Company;
  grant?: Grant;
  catalog: Catalog;
  /** Actions the person editing may grant here (an accountant cannot grant what it lacks). */
  allowed: (action: string) => boolean;
  disabled: boolean;
  onChange: (grant: Grant | null) => void;
}) {
  const actions = grant?.actions ?? [];
  const template = !grant ? '' : catalog.templates.find((t) => sameActions(t.actions, actions))?.id || 'custom';
  const [custom, setCustom] = useState(template === 'custom');
  const choose = (value: string) => {
    if (!value) return onChange(null);
    if (value === 'custom') {
      setCustom(true);
      return onChange({ company_id: company.id, access: actions.length ? 'write' : 'read', actions });
    }
    setCustom(false);
    const chosen = catalog.templates.find((t) => t.id === value)!.actions.filter(allowed);
    onChange({ company_id: company.id, access: chosen.length ? 'write' : 'read', actions: chosen });
  };
  const toggle = (action: string, on: boolean) => {
    const next = on ? [...actions, action] : actions.filter((a) => a !== action);
    onChange({ company_id: company.id, access: next.length ? 'write' : 'read', actions: next.sort() });
  };
  return (
    <fieldset className="account-grant" disabled={disabled}>
      <legend>
        {company.name} · {company.rfc}
      </legend>
      <select
        aria-label={'Permiso para ' + company.name}
        value={custom && grant ? 'custom' : template}
        onChange={(e) => choose(e.target.value)}
      >
        <option value="">Sin acceso</option>
        {catalog.templates.map((t) => (
          <option key={t.id} value={t.id}>
            {t.label}
          </option>
        ))}
        <option value="custom">Personalizado</option>
      </select>
      {grant && (custom || template === 'custom') && (
        <div className="account-actions">
          {catalog.actions.map((a) => (
            <label key={a.id} className="check-option">
              <input
                type="checkbox"
                checked={actions.includes(a.id)}
                disabled={!allowed(a.id)}
                onChange={(e) => toggle(a.id, e.target.checked)}
              />
              {a.label}
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}

function Editor({
  account,
  companies,
  identity,
  onClose,
  onSaved,
}: {
  account?: Account;
  companies: Company[];
  identity: CurrentUser;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [username, setUsername] = useState(account?.username || '');
  const [name, setName] = useState(account?.display_name || '');
  const [password, setPassword] = useState('');
  // An accountant only manages auxiliaries (Bloque 2); the server enforces it as well.
  const [role, setRole] = useState<Role>(account?.role || 'auxiliar');
  const [enabled, setEnabled] = useState(account?.enabled ?? true);
  const [grants, setGrants] = useState<Grant[]>(account?.grants || []);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const c = new AbortController();
    api<Catalog>('/auth/catalog', 'GET', undefined, c.signal)
      .then(setCatalog)
      .catch((e) => {
        if (!c.signal.aborted) setError((e as Error).message);
      });
    return () => c.abort();
  }, []);
  // An accountant grants only in the companies where it has write access, and only actions it holds there.
  const manageable = identity.admin ? companies : companies.filter((c) => identity.write_company_ids.includes(c.id));
  const setGrant = (companyId: string, grant: Grant | null) =>
    setGrants((old) => [...old.filter((g) => g.company_id !== companyId), ...(grant ? [grant] : [])]);
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    // Explicit actions only describe auxiliaries; other roles send the plain read/write grant.
    const payload = grants.map((g) =>
      role === 'auxiliar'
        ? { company_id: g.company_id, access: g.access, actions: g.actions ?? null }
        : { company_id: g.company_id, access: g.access },
    );
    try {
      if (account)
        await api('/auth/users/' + account.id, 'PUT', {
          revision: account.revision,
          display_name: name,
          role,
          enabled,
          grants: role === 'admin' ? [] : payload,
          ...(password ? { password } : {}),
        });
      else
        await api('/auth/users', 'POST', {
          username,
          display_name: name,
          password,
          role,
          enabled,
          grants: role === 'admin' ? [] : payload,
        });
      setPassword('');
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={account ? 'Editar usuario' : identity.admin ? 'Crear usuario' : 'Crear auxiliar'}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <form className="padded" onSubmit={save}>
        <div className="form-grid">
          <Field label="Usuario">
            <input
              required
              disabled={busy || !!account}
              minLength={3}
              maxLength={64}
              pattern="[a-zA-Z0-9_.\-]+"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </Field>
          <Field label="Nombre">
            <input required disabled={busy} maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label={account ? 'Nueva contraseña (opcional)' : 'Contraseña inicial'} wide>
            <input
              type="password"
              required={!account}
              disabled={busy}
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Field label="Rol">
            <select
              aria-label="Rol"
              disabled={busy || !identity.admin}
              value={role}
              onChange={(e) => {
                const next = e.target.value as Role;
                setRole(next);
                // Actions belong to auxiliaries; switching role starts from plain grants.
                setGrants((old) => old.map((g) => ({ company_id: g.company_id, access: g.access })));
              }}
            >
              <option value="auxiliar">{ROLE_LABELS.auxiliar}</option>
              {identity.admin && <option value="contador">{ROLE_LABELS.contador}</option>}
              {identity.admin && <option value="admin">{ROLE_LABELS.admin}</option>}
            </select>
          </Field>
          <Field label="Estado">
            <select
              aria-label="Estado"
              disabled={busy}
              value={enabled ? 'active' : 'disabled'}
              onChange={(e) => setEnabled(e.target.value === 'active')}
            >
              <option value="active">Activo</option>
              <option value="disabled">Desactivado</option>
            </select>
          </Field>
        </div>
        {role === 'admin' ? (
          <p className="muted">
            La administración tiene acceso a todas las empresas y a la configuración. No puede ser responsable de una
            empresa.
          </p>
        ) : role === 'contador' ? (
          <div className="account-grants">
            <p className="muted">
              Con escritura, el contador opera todo lo contable y fiscal de la empresa. El contador responsable se
              asigna desde el expediente.
            </p>
            {manageable.map((c) => (
              <Field key={c.id} label={c.name + ' · ' + c.rfc}>
                <select
                  aria-label={'Permiso para ' + c.name}
                  disabled={busy}
                  value={grants.find((g) => g.company_id === c.id)?.access || ''}
                  onChange={(e) => setGrant(c.id, e.target.value ? { company_id: c.id, access: e.target.value } : null)}
                >
                  <option value="">Sin acceso</option>
                  <option value="read">Lectura</option>
                  <option value="write">Lectura y escritura</option>
                </select>
              </Field>
            ))}
          </div>
        ) : !catalog ? (
          <p role="status">Consultando permisos…</p>
        ) : (
          <div className="account-grants">
            <p className="muted">
              El auxiliar siempre puede consultar las empresas asignadas. Elige una plantilla o personaliza sus
              acciones.
            </p>
            {manageable.map((c) => (
              <AuxiliaryGrant
                key={c.id}
                company={c}
                grant={grants.find((g) => g.company_id === c.id)}
                catalog={catalog}
                allowed={(a) => can(identity, a as Action, c.id)}
                disabled={busy}
                onChange={(g) => setGrant(c.id, g)}
              />
            ))}
            {!manageable.length && <p className="muted">No tienes empresas con escritura para asignar.</p>}
          </div>
        )}
        {error && (
          <p className="error-banner" role="alert">
            {error}
          </p>
        )}
        <div className="form-footer">
          <button type="button" className={stitchButton} disabled={busy} onClick={onClose}>
            Cancelar
          </button>
          <button className={stitchPrimary} disabled={busy}>
            {busy ? 'Guardando…' : 'Guardar cuenta'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
