import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
  AlertTriangle,
  Building2,
  Copy,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  HeartPulse,
  History,
  Home,
  KeyRound,
  Landmark,
  Lock,
  Mail,
  Paperclip,
  Pencil,
  ReceiptText,
  Repeat,
  Search,
  ShieldAlert,
  ShieldCheck,
  Upload,
  Wallet,
  WandSparkles,
  type LucideIcon,
} from 'lucide-react';
import { api, authHeaders } from '../api';
import { Badge, Field, Modal } from '../components/ui';
import { stitchButton, stitchCard, stitchDanger, stitchPrimary } from '../components/stitch';
import './v11.css';

/** Plan v1.1, Cambio 4: password manager per company and portal (Chrome-style) on the existing vault. */
type Item = {
  id: string;
  company_id: string;
  company_name: string;
  company_rfc: string;
  service_id: string;
  portal: string;
  label: string;
  username: string | null;
  url: string | null;
  notes: string | null;
  extra: Record<string, string> | null;
  holder: 'company' | 'legal_rep' | null;
  strength: number | null;
  repeated: boolean;
  revision: number;
  files: { id: string; kind: string; name: string }[];
  can_reveal: boolean;
  can_modify: boolean;
};
type Vault = {
  items: Item[];
  services: { id: string; label: string }[];
  companies: { id: string; name: string; rfc: string; can_create: boolean }[];
  health: { weak: number; repeated: number; unknown: number };
  vault_unlocked: boolean;
  can_export: boolean;
};
const FILE_PORTALS = ['fiel', 'csd', 'imss_certificate', 'fiel_password', 'csd_password'];
const STRENGTH = ['Muy débil', 'Débil', 'Regular', 'Buena', 'Fuerte'];
// Rediseño v2: signatures shown as cards; every other portal as a row with its icon.
const SIGNATURES = ['fiel', 'csd', 'fiel_password', 'csd_password'];
function portalIcon(service: string): LucideIcon {
  if (service === 'sat_password') return Landmark;
  if (/^(idse|sipare|imss)/.test(service)) return HeartPulse;
  if (service.startsWith('infonavit')) return Home;
  if (service === 'state_isn' || service === 'payroll_tax') return Building2;
  if (service === 'email') return Mail;
  if (service === 'fel' || service === 'external_billing' || service === 'contpaqi_payroll') return ReceiptText;
  if (service === 'bank') return Wallet;
  return KeyRound;
}
type LogRow = { id: string; actor_id: string; action: string; record_id: string | null; created_at: string };
const LOG_ACTIONS: Record<string, string> = {
  secret_revealed: 'Vio una contraseña',
  secret_copied: 'Copió una contraseña',
  reveal_blocked: 'Intento de ver o copiar sin permiso o sin reautenticación',
  reauth_confirmed: 'Confirmó su contraseña',
  reauth_failed: 'Contraseña de confirmación incorrecta',
  reauth_required: 'Se pidió confirmar la contraseña',
  autofill_ticket_issued: 'Usó el acceso con la extensión',
  credential_created: 'Creó un acceso',
  credential_modified: 'Modificó un acceso',
  secret_changed: 'Cambió una contraseña',
  credential_archived: 'Archivó un acceso',
  vault_file_stored: 'Cargó un archivo cifrado',
  vault_file_removed: 'Quitó un archivo cifrado',
  vault_exported: 'Exportó contraseñas',
  vault_import_previewed: 'Revisó una importación',
  vault_imported: 'Importó contraseñas',
  vault_listed: 'Consultó el gestor',
  vault_unlocked: 'Desbloqueó la bóveda',
  certificate_created: 'Registró un certificado',
  permission_changed: 'Cambió permisos',
  history_read: 'Consultó la bitácora',
  metadata_read: 'Consultó las credenciales',
};

/** A strong password made in the browser (crypto.getRandomValues); it never leaves the page until saved. */
export function generatePassword(length = 16, symbols = true) {
  const sets = [
    'ABCDEFGHJKLMNPQRSTUVWXYZ',
    'abcdefghijkmnopqrstuvwxyz',
    '23456789',
    ...(symbols ? ['!#$%&*+-=?@_'] : []),
  ];
  const all = sets.join('');
  const pick = (chars: string) => chars[crypto.getRandomValues(new Uint32Array(1))[0] % chars.length];
  const out = sets.map(pick);
  while (out.length < length) out.push(pick(all));
  for (let i = out.length - 1; i > 0; i--) {
    const j = crypto.getRandomValues(new Uint32Array(1))[0] % (i + 1);
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out.join('');
}

/** Local estimate shown while typing (the server computes the stored one the same way). */
export function localStrength(s: string) {
  if (!s) return 0;
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^a-zA-Z0-9]/].filter((r) => r.test(s)).length;
  let score =
    (s.length >= 8 ? 1 : 0) +
    (s.length >= 12 ? 1 : 0) +
    (classes >= 3 ? 1 : 0) +
    (classes === 4 && s.length >= 10 ? 1 : 0);
  if (/password|contrase|qwerty|123456|admin/i.test(s) || new Set(s).size <= 3) score = Math.min(score, 1);
  return score;
}

/** The ContaSuite browser extension marks the page when it is installed (plan v1.1, autocompletado SAT). */
function extensionReady() {
  return !!document.documentElement.dataset.contasuiteExtension;
}
function sendToExtension(message: Record<string, unknown>) {
  return new Promise<string>((resolve, reject) => {
    const id = crypto.randomUUID();
    const timer = setTimeout(() => {
      window.removeEventListener('message', listen);
      reject(new Error('La extensión de ContaSuite no respondió.'));
    }, 8000);
    function listen(e: MessageEvent) {
      if (e.source !== window || e.data?.source !== 'contasuite-extension' || e.data?.id !== id) return;
      clearTimeout(timer);
      window.removeEventListener('message', listen);
      if (e.data.ok) resolve(e.data.message || 'Listo');
      else reject(new Error(e.data.message || 'La extensión no pudo completar el inicio de sesión.'));
    }
    window.addEventListener('message', listen);
    window.postMessage({ source: 'contasuite-page', id, ...message }, window.location.origin);
  });
}

export default function PasswordManager({
  companyId,
  notify,
  users = {},
}: {
  companyId?: string;
  notify: (s: string) => void;
  /** Names of the people the page already knows (id → name), to show in the log instead of internal ids. */
  users?: Record<string, string>;
}) {
  const [data, setData] = useState<Vault | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [service, setService] = useState('');
  const [reload, setReload] = useState(0);
  const [shown, setShown] = useState<Record<string, string>>({});
  const [reauth, setReauth] = useState<null | (() => Promise<void>)>(null);
  const [editing, setEditing] = useState<Item | 'new' | null>(null);
  const [filesOf, setFilesOf] = useState<Item | null>(null);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [generator, setGenerator] = useState(false);
  const [selected, setSelected] = useState('');
  const [tab, setTab] = useState<'credentials' | 'log'>('credentials');
  const [log, setLog] = useState<LogRow[] | null>(null);
  const timers = useRef<Record<string, number>>({});
  useEffect(() => {
    const abort = new AbortController();
    const t = setTimeout(() => {
      const q = new URLSearchParams({ query, service, ...(companyId ? { company_id: companyId } : {}) });
      api<Vault>('/credentials/vault?' + q, 'GET', undefined, abort.signal)
        .then((d) => {
          setData(d);
          setError('');
        })
        .catch((e) => !abort.signal.aborted && setError(e.message));
    }, 250);
    return () => {
      clearTimeout(t);
      abort.abort();
    };
  }, [query, service, companyId, reload]);
  useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), []);

  /** Runs `action`; when the server asks for the password again, opens the dialog and retries after it. */
  async function withReauth(action: () => Promise<void>) {
    try {
      await action();
    } catch (e) {
      if (/Confirma tu contraseña/.test((e as Error).message)) setReauth(() => action);
      else notify((e as Error).message);
    }
  }
  function hide(id: string) {
    setShown((old) => {
      const next = { ...old };
      delete next[id];
      return next;
    });
  }
  async function reveal(item: Item) {
    if (shown[item.id]) return hide(item.id);
    await withReauth(async () => {
      const r = await api<{ secret: string; expires_in: number }>(
        `/credentials/companies/${item.company_id}/secrets/${item.id}/reveal`,
        'POST',
        { action: 'view' },
      );
      setShown((old) => ({ ...old, [item.id]: r.secret }));
      clearTimeout(timers.current[item.id]);
      timers.current[item.id] = window.setTimeout(() => hide(item.id), r.expires_in * 1000);
    });
  }
  async function copy(item: Item) {
    await withReauth(async () => {
      const r = await api<{ secret: string }>(
        `/credentials/companies/${item.company_id}/secrets/${item.id}/reveal`,
        'POST',
        {
          action: 'copy',
        },
      );
      await navigator.clipboard.writeText(r.secret);
      notify('Contraseña copiada; el portapapeles se limpia en 30 segundos.');
      window.setTimeout(() => {
        navigator.clipboard.writeText('').catch(() => undefined);
      }, 30000);
    });
  }
  async function autofill(item: Item, purpose: 'sat_password' | 'sat_fiel') {
    if (!extensionReady()) {
      notify('Instala la extensión de ContaSuite en Chrome o Edge para entrar al portal del SAT con autocompletado.');
      return;
    }
    await withReauth(async () => {
      const r = await api<{ ticket: string }>(
        `/credentials/companies/${item.company_id}/secrets/${item.id}/ticket`,
        'POST',
        {
          purpose,
        },
      );
      notify(await sendToExtension({ type: 'autofill', purpose, ticket: r.ticket, server: window.location.origin }));
    });
  }
  async function archive(item: Item) {
    if (!confirm(`¿Archivar el acceso «${item.portal}» de ${item.company_name}? Queda en el historial.`)) return;
    try {
      await api(`/credentials/companies/${item.company_id}/secrets/${item.id}?revision=${item.revision}`, 'DELETE');
      setReload((n) => n + 1);
    } catch (e) {
      notify((e as Error).message);
    }
  }
  const items = data?.items || [];
  // Rediseño v2: list of companies on the left (office view) and the selected company on the right.
  const q = query.trim().toLowerCase();
  const companies = (data?.companies || []).filter(
    (c) => !q || (c.name + ' ' + c.rfc).toLowerCase().includes(q) || items.some((i) => i.company_id === c.id),
  );
  const current = companyId || (companies.some((c) => c.id === selected) ? selected : companies[0]?.id) || '';
  const currentCompany = data?.companies.find((c) => c.id === current);
  const mine = items.filter((i) => i.company_id === current);
  // FIEL of the company, FIEL of the legal representative, then the CSD (order of the design).
  const signatureOrder = (i: Item) => (i.service_id.startsWith('csd') ? 2 : i.holder === 'legal_rep' ? 1 : 0);
  const signatures = mine
    .filter((i) => SIGNATURES.includes(i.service_id))
    .sort((a, b) => signatureOrder(a) - signatureOrder(b));
  const portals = mine.filter((i) => !SIGNATURES.includes(i.service_id));
  async function openLog() {
    setTab('log');
    setLog(null);
    try {
      setLog(await api<LogRow[]>(`/credentials/companies/${current}/history`));
    } catch (e) {
      setLog([]);
      notify((e as Error).message);
    }
  }
  const secretActions = (item: Item, compact: boolean) => (
    <>
      {item.can_reveal && (
        <>
          <button
            className={stitchButton + (compact ? ' icon-only' : '')}
            aria-label={(shown[item.id] ? 'Ocultar' : 'Mostrar') + ' contraseña de ' + item.portal}
            onClick={() => reveal(item)}
          >
            {shown[item.id] ? <EyeOff size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
            {!compact && (shown[item.id] ? 'Ocultar' : 'Mostrar')}
          </button>
          <button
            className={stitchButton + (compact ? ' icon-only' : '')}
            aria-label={'Copiar contraseña de ' + item.portal}
            onClick={() => copy(item)}
          >
            <Copy size={16} aria-hidden />
            {!compact && 'Copiar'}
          </button>
          {(item.service_id === 'sat_password' || item.service_id === 'fiel') && (
            <button
              className={compact ? stitchButton : stitchPrimary}
              title="Abre el portal del SAT y llena el acceso con la extensión de ContaSuite"
              onClick={() => autofill(item, item.service_id === 'fiel' ? 'sat_fiel' : 'sat_password')}
            >
              <ExternalLink size={16} aria-hidden /> Entrar al SAT
            </button>
          )}
        </>
      )}
      {item.can_modify && (
        <>
          <button
            className={stitchButton + ' icon-only'}
            aria-label={'Editar ' + item.portal}
            onClick={() => setEditing(item)}
          >
            <Pencil size={16} aria-hidden />
          </button>
          {FILE_PORTALS.includes(item.service_id) && (
            <button
              className={stitchButton + ' icon-only'}
              aria-label={'Archivos de ' + item.portal}
              onClick={() => setFilesOf(item)}
            >
              <Paperclip size={16} aria-hidden />
            </button>
          )}
          <button className={stitchDanger} onClick={() => archive(item)}>
            Archivar
          </button>
        </>
      )}
    </>
  );
  const flags = (item: Item) => (
    <>
      {item.strength != null && item.strength <= 1 && (
        <span className="v2-flag is-weak">
          <AlertTriangle size={12} aria-hidden /> {STRENGTH[item.strength]}
        </span>
      )}
      {item.repeated && (
        <span className="v2-flag is-repeated">
          <Repeat size={12} aria-hidden /> Repetida
        </span>
      )}
    </>
  );
  return (
    <section className="v11-vault v2-vault">
      <div className="v2-vault-top">
        {data && (data.health.weak > 0 || data.health.repeated > 0) ? (
          <p className="v2-vault-health" role="status">
            <ShieldAlert size={16} aria-hidden /> Revisión: {data.health.weak} contraseñas débiles,{' '}
            {data.health.repeated} repetidas <span>(revisión local, sin servicios externos)</span>
          </p>
        ) : (
          data && (
            <p className="v2-vault-health is-ok" role="status">
              <ShieldCheck size={16} aria-hidden /> Sin contraseñas débiles ni repetidas (revisión local)
            </p>
          )
        )}
        <div className="actions">
          {data?.can_export && (
            <>
              <button className={stitchButton} onClick={() => setImporting(true)}>
                <Upload size={16} aria-hidden /> Importar desde Excel
              </button>
              <button className={stitchButton} onClick={() => setExporting(true)}>
                <Download size={16} aria-hidden /> Exportar
              </button>
            </>
          )}
          <button
            className={stitchButton}
            disabled={!data?.companies.some((c) => c.can_create)}
            onClick={() => setEditing('new')}
          >
            <KeyRound size={16} aria-hidden /> Nueva credencial
          </button>
          <button className={stitchPrimary} onClick={() => setGenerator(true)}>
            <WandSparkles size={16} aria-hidden /> Generar contraseña
          </button>
        </div>
      </div>
      <p className="muted v2-vault-note">
        <Lock size={14} aria-hidden /> Cifradas en el servidor. Para ver, copiar o usar una contraseña se pide de nuevo
        tu contraseña y queda en la bitácora. No guardes contraseñas en nombres ni notas.
      </p>
      {data && !data.vault_unlocked && (
        <p role="alert" className="error-banner">
          La bóveda está bloqueada: falta el llavero maestro del servidor (scripts/vault_keyring.py). Puedes consultar
          los registros, pero no guardar ni ver contraseñas.
        </p>
      )}
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      <div className={'v2-vault-layout' + (companyId ? ' is-single' : '')}>
        {!companyId && (
          <aside className="v2-vault-companies" aria-label="Empresas del gestor">
            <label className="v2-search">
              <Search size={16} aria-hidden />
              <input
                aria-label="Buscar empresa, portal o usuario"
                placeholder="Buscar empresa, RFC, portal o usuario"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <ul>
              {companies.map((c) => {
                const count = items.filter((i) => i.company_id === c.id).length;
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      aria-pressed={c.id === current}
                      onClick={() => {
                        setSelected(c.id);
                        setTab('credentials');
                      }}
                    >
                      <strong>{c.name}</strong>
                      <small>
                        <span className="rfc">{c.rfc}</span> · {count} {count === 1 ? 'acceso' : 'accesos'}
                      </small>
                    </button>
                  </li>
                );
              })}
              {data && !companies.length && <li className="muted">Sin empresas con estos filtros.</li>}
            </ul>
          </aside>
        )}
        <div className="v2-vault-detail">
          {currentCompany && (
            <header className="v2-vault-company">
              <div>
                <h2>{currentCompany.name}</h2>
                <span className="rfc">{currentCompany.rfc}</span>
              </div>
              <select aria-label="Portal" value={service} onChange={(e) => setService(e.target.value)}>
                <option value="">Todos los portales</option>
                {data?.services.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </header>
          )}
          {currentCompany && (
            <div className="v2-segmented" role="group" aria-label="Sección del gestor">
              <button type="button" aria-pressed={tab === 'credentials'} onClick={() => setTab('credentials')}>
                <KeyRound size={16} aria-hidden /> Credenciales
              </button>
              <button type="button" aria-pressed={tab === 'log'} onClick={openLog}>
                <History size={16} aria-hidden /> Bitácora de accesos
              </button>
            </div>
          )}
          {tab === 'credentials' && currentCompany && (
            <>
              <h3 className="v2-vault-heading">Firmas electrónicas</h3>
              {signatures.length ? (
                <div className="v2-signatures">
                  {signatures.map((item) => (
                    <article key={item.id} className="v2-signature">
                      <header>
                        <h4>
                          {item.service_id.startsWith('csd')
                            ? 'Sello digital (CSD)'
                            : item.holder === 'legal_rep'
                              ? 'FIEL del representante'
                              : 'FIEL de la empresa'}
                        </h4>
                        {flags(item)}
                      </header>
                      <small className="muted">
                        {item.portal}
                        {item.label && item.label !== 'Acceso' && ' · ' + item.label}
                        {item.username && (
                          <>
                            {' · '}
                            <span className="rfc">{item.username}</span>
                          </>
                        )}
                      </small>
                      {item.files.length > 0 ? (
                        <ul className="v2-files" aria-label="Archivos cifrados">
                          {item.files.map((f) => (
                            <li key={f.id}>
                              <Lock size={13} aria-hidden /> {f.name}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <small className="muted">Sin archivos .cer / .key cargados.</small>
                      )}
                      <div className="v2-secret">
                        <span aria-live="polite">{shown[item.id] ?? '••••••••••••'}</span>
                      </div>
                      <div className="actions">{secretActions(item, false)}</div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="v2-empty muted">No hay FIEL ni sello digital registrados para esta empresa.</p>
              )}
              <h3 className="v2-vault-heading">Accesos a portales</h3>
              {portals.length ? (
                <ul className="v2-portals">
                  {portals.map((item) => {
                    const Icon = portalIcon(item.service_id);
                    return (
                      <li key={item.id}>
                        <Icon size={20} aria-hidden className="v2-portal-icon" />
                        <div className="v2-portal-name">
                          <strong>
                            {item.portal}
                            {item.label && item.label !== 'Acceso' && ' · ' + item.label}
                          </strong>
                          {item.username ? (
                            <button
                              className="link-button rfc"
                              title="Copiar usuario"
                              onClick={() =>
                                navigator.clipboard.writeText(item.username!).then(() => notify('Usuario copiado'))
                              }
                            >
                              {item.username}
                            </button>
                          ) : (
                            <span className="muted">Sin usuario</span>
                          )}
                          {item.holder === 'legal_rep' && <Badge tone="blue">Representante legal</Badge>}
                          {flags(item)}
                        </div>
                        <span className="v2-secret-inline" aria-live="polite">
                          {shown[item.id] ?? '••••••••••••'}
                        </span>
                        <div className="actions">{secretActions(item, true)}</div>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="v2-empty muted">No hay accesos a portales con estos filtros.</p>
              )}
            </>
          )}
          {tab === 'log' && currentCompany && (
            <div className="v2-vault-log">
              {log === null ? (
                <p role="status">Consultando bitácora…</p>
              ) : log.length ? (
                <table className="v2-list">
                  <thead>
                    <tr>
                      <th scope="col">Fecha</th>
                      <th scope="col">Usuario</th>
                      <th scope="col">Acción</th>
                      <th scope="col">Acceso</th>
                    </tr>
                  </thead>
                  <tbody>
                    {log.map((r) => (
                      <tr key={r.id}>
                        <td>{new Date(r.created_at).toLocaleString('es-MX')}</td>
                        <td>{users[r.actor_id] || r.actor_id}</td>
                        <td>{LOG_ACTIONS[r.action] || r.action}</td>
                        <td>{items.find((i) => i.id === r.record_id)?.portal || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted">Sin movimientos registrados o sin permiso para consultar la bitácora.</p>
              )}
              <p className="muted small">Cada consulta de esta bitácora también queda registrada.</p>
            </div>
          )}
          {data && !currentCompany && <p className="v2-empty muted">No hay empresas con accesos para mostrar.</p>}
        </div>
      </div>
      {reauth && (
        <ReauthDialog
          onClose={() => setReauth(null)}
          onDone={async () => {
            const retry = reauth;
            setReauth(null);
            await retry().catch((e) => notify((e as Error).message));
          }}
        />
      )}
      {editing && data && (
        <CredentialForm
          item={editing === 'new' ? null : editing}
          companyId={companyId}
          vault={data}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setReload((n) => n + 1);
            notify('Credencial guardada cifrada.');
          }}
        />
      )}
      {filesOf && (
        <FilesDialog
          item={filesOf}
          onClose={() => setFilesOf(null)}
          onChanged={() => setReload((n) => n + 1)}
          notify={notify}
        />
      )}
      {generator && <GeneratorDialog onClose={() => setGenerator(false)} notify={notify} />}
      {importing && (
        <ImportDialog onClose={() => setImporting(false)} onDone={() => setReload((n) => n + 1)} notify={notify} />
      )}
      {exporting && data && (
        <ExportDialog
          companies={data.companies}
          companyId={companyId}
          onClose={() => setExporting(false)}
          onNeedReauth={(retry) => setReauth(() => retry)}
          notify={notify}
        />
      )}
    </section>
  );
}

function ReauthDialog({ onClose, onDone }: { onClose: () => void; onDone: () => Promise<void> }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const field = useRef<HTMLInputElement>(null);
  // The dialog focuses its close button first; the password field is what the person types into.
  useEffect(() => {
    const t = window.setTimeout(() => field.current?.focus(), 0);
    return () => clearTimeout(t);
  }, []);
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api('/credentials/reauth', 'POST', { password });
      setPassword('');
      await onDone();
    } catch (err) {
      setPassword('');
      setError((err as Error).message);
    }
  }
  return (
    <Modal title="Confirma tu contraseña" onClose={onClose}>
      <form onSubmit={submit} className="form-grid">
        <p className="wide">
          Por seguridad, ver, copiar o usar secretos pide tu contraseña de ContaSuite. Vale cinco minutos.
        </p>
        <Field label="Tu contraseña de ContaSuite">
          <input
            ref={field}
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {error && (
          <p role="alert" className="error-banner wide">
            {error}
          </p>
        )}
        <div className="actions wide">
          <button type="button" className={stitchButton} onClick={onClose}>
            Cancelar
          </button>
          <button className={stitchPrimary}>Confirmar</button>
        </div>
      </form>
    </Modal>
  );
}

function CredentialForm({
  item,
  companyId,
  vault,
  onClose,
  onSaved,
}: {
  item: Item | null;
  companyId?: string;
  vault: Vault;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    company_id: item?.company_id || companyId || '',
    service_id: item?.service_id || 'sat_password',
    label: item?.label && item.label !== 'Acceso' ? item.label : '',
    holder: item?.holder || 'company',
    username: item?.username || '',
    url: item?.url || '',
    notes: item?.notes || '',
    registro: item?.extra?.registro_patronal || '',
  });
  const [secret, setSecret] = useState('');
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState('');
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const score = localStrength(secret);
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api(
        `/credentials/companies/${form.company_id}/secrets` + (item ? '?ident=' + encodeURIComponent(item.id) : ''),
        'POST',
        {
          service_id: form.service_id,
          label: form.label.trim() || 'Acceso',
          username: form.username || null,
          url: form.url || null,
          notes: form.notes || null,
          extra: form.registro ? { registro_patronal: form.registro } : {},
          holder: ['fiel', 'csd', 'fiel_password', 'csd_password'].includes(form.service_id) ? form.holder : null,
          revision: item?.revision || 0,
          ...(secret ? { secret } : {}),
        },
      );
      setSecret('');
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <Modal title={item ? 'Editar acceso' : 'Nueva credencial'} onClose={onClose}>
      <form className="form-grid" onSubmit={submit} autoComplete="off">
        {!companyId && !item && (
          <Field label="Empresa">
            <select required value={form.company_id} onChange={(e) => set('company_id', e.target.value)}>
              <option value="">Elige la empresa</option>
              {vault.companies
                .filter((c) => c.can_create)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} · {c.rfc}
                  </option>
                ))}
            </select>
          </Field>
        )}
        <Field label="Portal">
          <select value={form.service_id} disabled={!!item} onChange={(e) => set('service_id', e.target.value)}>
            {vault.services.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Nombre (opcional, sin contraseñas)">
          <input maxLength={100} value={form.label} onChange={(e) => set('label', e.target.value)} />
        </Field>
        {['fiel', 'csd', 'fiel_password', 'csd_password'].includes(form.service_id) && (
          <Field label="Titular">
            <select value={form.holder} onChange={(e) => set('holder', e.target.value)}>
              <option value="company">La empresa</option>
              <option value="legal_rep">Representante legal</option>
            </select>
          </Field>
        )}
        <Field label="Usuario">
          <input
            maxLength={200}
            autoComplete="off"
            value={form.username}
            onChange={(e) => set('username', e.target.value)}
          />
        </Field>
        <Field label={item ? 'Contraseña nueva (vacía = conservar la actual)' : 'Contraseña'}>
          <input
            type={visible ? 'text' : 'password'}
            autoComplete="new-password"
            required={!item}
            maxLength={4096}
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
          <div className="actions">
            <button type="button" className={stitchButton} onClick={() => setVisible((v) => !v)}>
              {visible ? 'Ocultar' : 'Mostrar'}
            </button>
            <button
              type="button"
              className={stitchButton}
              onClick={() => {
                setSecret(generatePassword());
                setVisible(true);
              }}
            >
              <WandSparkles size={16} aria-hidden /> Generar
            </button>
            {secret && <small className={score <= 1 ? 'v11-weak' : ''}>Fortaleza: {STRENGTH[score]}</small>}
          </div>
        </Field>
        <Field label="Dirección del portal (opcional)">
          <input
            type="url"
            maxLength={500}
            placeholder="https://"
            value={form.url}
            onChange={(e) => set('url', e.target.value)}
          />
        </Field>
        {['idse', 'sipare', 'infonavit', 'imss_registration', 'imss_certificate'].includes(form.service_id) && (
          <Field label="Registro patronal">
            <input maxLength={20} value={form.registro} onChange={(e) => set('registro', e.target.value)} />
          </Field>
        )}
        <Field label="Notas (no escribas contraseñas aquí)">
          <textarea rows={2} maxLength={2000} value={form.notes} onChange={(e) => set('notes', e.target.value)} />
        </Field>
        {error && (
          <p role="alert" className="error-banner wide">
            {error}
          </p>
        )}
        <div className="actions wide">
          <button type="button" className={stitchButton} onClick={onClose}>
            Cancelar
          </button>
          <button className={stitchPrimary}>Guardar cifrada</button>
        </div>
      </form>
    </Modal>
  );
}

function FilesDialog({
  item,
  onClose,
  onChanged,
  notify,
}: {
  item: Item;
  onClose: () => void;
  onChanged: () => void;
  notify: (s: string) => void;
}) {
  const [files, setFiles] = useState(item.files);
  const input = useRef<HTMLInputElement>(null);
  async function upload(file: File) {
    const body = new FormData();
    body.append('file', file);
    try {
      const r = await api<{ id: string; kind: string }>(
        `/credentials/companies/${item.company_id}/secrets/${item.id}/files`,
        'POST',
        body,
      );
      setFiles((old) => [...old.filter((f) => f.kind !== r.kind), { id: r.id, kind: r.kind, name: file.name }]);
      onChanged();
      notify(
        r.kind === 'cer'
          ? 'Certificado guardado; sus fechas alimentan el semáforo (no es validación SAT).'
          : 'Llave privada guardada cifrada.',
      );
    } catch (e) {
      notify((e as Error).message);
    } finally {
      if (input.current) input.current.value = '';
    }
  }
  async function remove(id: string) {
    try {
      await api(`/credentials/companies/${item.company_id}/secrets/${item.id}/files/${id}`, 'DELETE');
      setFiles((old) => old.filter((f) => f.id !== id));
      onChanged();
    } catch (e) {
      notify((e as Error).message);
    }
  }
  return (
    <Modal title={`Archivos · ${item.portal}`} onClose={onClose}>
      <p>
        El .cer y el .key se guardan cifrados fuera de las carpetas de documentos; no se indexan ni se descargan. Se
        usan sólo con la extensión de ContaSuite al entrar al SAT.
      </p>
      <ul>
        {files.map((f) => (
          <li key={f.id}>
            .{f.kind} · {f.name}{' '}
            <button className={stitchButton} onClick={() => remove(f.id)}>
              Quitar
            </button>
          </li>
        ))}
        {!files.length && <li className="muted">Sin archivos.</li>}
      </ul>
      <input
        ref={input}
        type="file"
        accept=".cer,.key"
        hidden
        onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
      />
      <div className="actions">
        <button className={stitchPrimary} onClick={() => input.current?.click()}>
          <Upload size={16} aria-hidden /> Subir .cer o .key
        </button>
        <button className={stitchButton} onClick={onClose}>
          Cerrar
        </button>
      </div>
    </Modal>
  );
}

function GeneratorDialog({ onClose, notify }: { onClose: () => void; notify: (s: string) => void }) {
  const [length, setLength] = useState(16);
  const [symbols, setSymbols] = useState(true);
  const [value, setValue] = useState(() => generatePassword(16, true));
  return (
    <Modal title="Generador de contraseñas" onClose={onClose}>
      <p className="v11-secret" aria-live="polite">
        {value}
      </p>
      <div className="form-grid">
        <Field label={`Longitud: ${length}`}>
          <input type="range" min={10} max={40} value={length} onChange={(e) => setLength(Number(e.target.value))} />
        </Field>
        <label className="check-option">
          <input type="checkbox" checked={symbols} onChange={(e) => setSymbols(e.target.checked)} /> Incluir símbolos
        </label>
      </div>
      <div className="actions">
        <button className={stitchButton} onClick={() => setValue(generatePassword(length, symbols))}>
          <WandSparkles size={16} aria-hidden /> Otra
        </button>
        <button
          className={stitchPrimary}
          onClick={() =>
            navigator.clipboard.writeText(value).then(() => {
              notify('Contraseña copiada; el portapapeles se limpia en 30 segundos.');
              window.setTimeout(() => navigator.clipboard.writeText('').catch(() => undefined), 30000);
            })
          }
        >
          <Copy size={16} aria-hidden /> Copiar
        </button>
      </div>
      <p className="muted">
        Algunos portales (SAT, IMSS) limitan longitud o símbolos: revisa sus reglas antes de cambiarla.
      </p>
    </Modal>
  );
}

type PreviewRow = {
  row: number;
  sheets: string[];
  rfc: string | null;
  company_name: string | null;
  company_id: string | null;
  matched_name: string | null;
  company_fields: string[];
  entries: {
    service_id: string;
    portal: string;
    label: string;
    holder: string | null;
    has_user: boolean;
    has_password: boolean;
  }[];
  issues: string[];
  importable: boolean;
};

function ImportDialog({
  onClose,
  onDone,
  notify,
}: {
  onClose: () => void;
  onDone: () => void;
  notify: (s: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<{ sha256: string; rows: PreviewRow[] } | null>(null);
  const [chosen, setChosen] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  async function analyze(f: File) {
    setFile(f);
    setBusy(true);
    const body = new FormData();
    body.append('file', f);
    try {
      const p = await api<{ sha256: string; rows: PreviewRow[] }>('/credentials/import/preview', 'POST', body);
      setPreview(p);
      setChosen(new Set(p.rows.filter((r) => r.importable).map((r) => r.row)));
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function confirmImport() {
    if (!file || !preview) return;
    setBusy(true);
    const body = new FormData();
    body.append('file', file);
    body.append('sha256', preview.sha256);
    body.append('rows', [...chosen].join(','));
    try {
      const r = await api<{ created: number; kept_existing: number; skipped: number; company_fields_filled: number }>(
        '/credentials/import/confirm',
        'POST',
        body,
      );
      notify(
        `Importación: ${r.created} accesos nuevos, ${r.kept_existing} ya existían (sin cambios), ${r.skipped} omitidos, ${r.company_fields_filled} datos de empresa completados.`,
      );
      setFile(null);
      onDone();
      onClose();
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Importar contraseñas desde Excel" onClose={onClose}>
      <p>
        Acepta el Excel del despacho (una hoja) y el de corporativo (hojas EMPRESAS y CONTRASEÑAS). Se empareja por RFC
        exacto; lo que no coincide queda para revisión. La vista previa nunca muestra contraseñas y el archivo no se
        guarda.
      </p>
      <input
        type="file"
        accept=".xlsx"
        disabled={busy}
        onChange={(e) => e.target.files?.[0] && analyze(e.target.files[0])}
      />
      {preview && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Importar</th>
                <th scope="col">Fila</th>
                <th scope="col">RFC / empresa</th>
                <th scope="col">Accesos</th>
                <th scope="col">Revisión</th>
              </tr>
            </thead>
            <tbody>
              {preview.rows.map((r) => (
                <tr key={r.row}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={'Importar fila ' + r.row}
                      disabled={!r.importable}
                      checked={chosen.has(r.row)}
                      onChange={(e) =>
                        setChosen((old) => {
                          const next = new Set(old);
                          if (e.target.checked) next.add(r.row);
                          else next.delete(r.row);
                          return next;
                        })
                      }
                    />
                  </td>
                  <td>{r.row}</td>
                  <td>
                    {r.rfc || '—'}
                    <br />
                    <small>{r.matched_name || r.company_name || ''}</small>
                  </td>
                  <td>
                    {r.entries.map((e) => (
                      <div key={e.portal + e.label + (e.holder || '')}>
                        {e.portal}
                        {e.holder === 'legal_rep' ? ' (representante)' : ''}: usuario{' '}
                        {e.has_user ? 'presente' : 'vacío'} · contraseña {e.has_password ? 'presente' : 'vacía'}
                      </div>
                    ))}
                    {r.company_fields.length > 0 && <small>Datos de empresa: {r.company_fields.join(', ')}</small>}
                  </td>
                  <td>{r.issues.join(' ') || 'Lista'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="actions">
        <button className={stitchButton} onClick={onClose}>
          Cancelar
        </button>
        <button className={stitchPrimary} disabled={busy || !preview || !chosen.size} onClick={confirmImport}>
          Importar {chosen.size} filas
        </button>
      </div>
    </Modal>
  );
}

function ExportDialog({
  companies,
  companyId,
  onClose,
  onNeedReauth,
  notify,
}: {
  companies: Vault['companies'];
  companyId?: string;
  onClose: () => void;
  onNeedReauth: (retry: () => Promise<void>) => void;
  notify: (s: string) => void;
}) {
  const [reason, setReason] = useState('');
  const [onlyThis, setOnlyThis] = useState(!!companyId);
  async function run() {
    const response = await fetch('/api/credentials/export', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason, company_ids: onlyThis && companyId ? [companyId] : companies.map((c) => c.id) }),
    });
    if (response.status === 428) {
      onNeedReauth(run);
      return;
    }
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'No se pudo exportar.');
    const url = URL.createObjectURL(await response.blob());
    const a = document.createElement('a');
    a.href = url;
    a.download = 'contrasenas_contasuite.xlsx';
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    notify('Exportación lista. Protege el archivo y bórralo cuando termines.');
    onClose();
  }
  return (
    <Modal title="Exportar contraseñas" onClose={onClose}>
      <p role="alert" className="error-banner">
        El archivo tendrá las contraseñas en claro. Guárdalo cifrado, no lo envíes por correo y bórralo al terminar. La
        exportación queda en la bitácora con tu motivo.
      </p>
      <Field label="Motivo">
        <input required minLength={3} maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      {companyId && (
        <label className="check-option">
          <input type="checkbox" checked={onlyThis} onChange={(e) => setOnlyThis(e.target.checked)} /> Sólo esta empresa
        </label>
      )}
      <div className="actions">
        <button className={stitchButton} onClick={onClose}>
          Cancelar
        </button>
        <button
          className={stitchDanger}
          disabled={reason.trim().length < 3}
          onClick={() => run().catch((e) => notify(e.message))}
        >
          Exportar
        </button>
      </div>
    </Modal>
  );
}
