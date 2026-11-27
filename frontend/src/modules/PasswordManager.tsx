import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import {
  Clock,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  FileKey2,
  History,
  KeyRound,
  MoreHorizontal,
  MoreVertical,
  Plus,
  Search,
  Upload,
  WandSparkles,
} from 'lucide-react';
import { api } from '../api';
import { Field, Modal } from '../components/ui';
import { stitchButton, stitchPrimary } from '../components/stitch';
import { isLockedError, LockNow, useVault, VaultTimer } from './VaultGate';
import AddSignature, { type SignatureClass } from './AddSignature';
import { downloadTemplate, ExportDialog, ImportDialog } from './VaultImport';
import './v11.css';

/** Plan v1.1, Cambio 4 and renovación del gestor (fase 5): companies on the left, the selected company on the right
 *  with its signatures and its passwords by type (lienzo «Gestor de contraseñas · Principal»). */
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
  kind: string | null;
  requires_review: boolean | null;
  files: { id: string; kind: string; name: string }[];
  can_reveal: boolean;
  can_modify: boolean;
};
type Cert = {
  id: string;
  company_id: string;
  cert_class: SignatureClass;
  holder_name: string | null;
  holder_rfc: string | null;
  holder_curp: string | null;
  branch: string | null;
  number: string | null;
  valid_from: string | null;
  valid_until: string | null;
  days_left: number | null;
  validity: 'valid' | 'expiring' | 'expired' | 'unknown';
  active: boolean;
  replaced_by: string | null;
  incomplete: boolean;
  files: { cer?: string; key?: string };
  key_password_id: string | null;
};
type VaultCompany = {
  id: string;
  name: string;
  rfc: string;
  regime: string;
  person_type: string;
  can_create: boolean;
  fiel: { state: 'valid' | 'expiring' | 'expired' | 'unknown' | 'none'; days: number | null };
  certificate_count: number;
  password_count: number;
};
type Summary = {
  passwords: number;
  certificates: number;
  expiring: number;
  expired: number;
  weak_or_repeated: number;
  last_access: null | { at: string; kind: string; company: string | null; what: string | null; who: string | null };
};
type Vault = {
  items: Item[];
  certificates: Cert[];
  summary: Summary;
  services: { id: string; label: string }[];
  companies: VaultCompany[];
  health: { weak: number; repeated: number; unknown: number };
  vault_unlocked: boolean;
  can_export: boolean;
};
// Types of the spec, in the order of the design; LLAVE (password of a private key) lives on its certificate card.
const KINDS: [string, string][] = [
  ['SAT_CIEC', 'SAT'],
  ['IMSS_IDSE', 'IMSS'],
  ['SIPARE', 'SIPARE'],
  ['INFONAVIT', 'Infonavit'],
  ['CORREO', 'Correo'],
  ['OTRO', 'Otro'],
];
const CHIPS: [string, string][] = [
  ['all', 'Todos'],
  ['FIEL', 'FIEL'],
  ['CSD', 'CSD'],
  ['SAT_CIEC', 'SAT'],
  ['IMSS_IDSE', 'IMSS'],
  ['SIPARE', 'SIPARE'],
  ['INFONAVIT', 'Infonavit'],
  ['CORREO', 'Correo'],
];
const CLASS_LABELS: Record<SignatureClass, string> = {
  FIEL_EMPRESA: 'FIEL de la empresa',
  FIEL_REPRESENTANTE: 'FIEL del representante',
  CSD: 'Sello digital (CSD)',
};
const SERVICE_KIND: Record<string, string> = {
  sat_password: 'SAT_CIEC',
  idse: 'IMSS_IDSE',
  idse_user: 'IMSS_IDSE',
  idse_password: 'IMSS_IDSE',
  imss_certificate: 'IMSS_IDSE',
  sipare: 'SIPARE',
  sipare_user: 'SIPARE',
  sipare_password: 'SIPARE',
  infonavit: 'INFONAVIT',
  infonavit_user: 'INFONAVIT',
  infonavit_password: 'INFONAVIT',
  email: 'CORREO',
  fiel: 'LLAVE',
  csd: 'LLAVE',
  fiel_password: 'LLAVE',
  csd_password: 'LLAVE',
};
const STRENGTH = ['Muy débil', 'Débil', 'Regular', 'Buena', 'Fuerte'];
const kindOf = (i: Item) => i.kind || SERVICE_KIND[i.service_id] || 'OTRO';
/** «Segura», «Débil», «Repetida» or «Revisar» (checked locally, nothing is sent outside). */
function status(i: Item): { label: string; tone: 'ok' | 'warn' | 'danger' } {
  if (i.requires_review || i.strength == null) return { label: 'Revisar', tone: 'warn' };
  if (i.repeated) return { label: 'Repetida', tone: 'warn' };
  if (i.strength <= 1) return { label: 'Débil', tone: 'danger' };
  return { label: 'Segura', tone: 'ok' };
}
const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('es-MX') : '—');
function validityText(c: Cert) {
  if (c.incomplete) return 'Faltan .cer y .key';
  if (c.validity === 'expired') return `Vencido el ${day(c.valid_until)}`;
  if (c.validity === 'expiring') return `Vence en ${c.days_left} ${c.days_left === 1 ? 'día' : 'días'}`;
  if (c.validity === 'valid') return `Vigente hasta ${day(c.valid_until)} · faltan ${c.days_left} días`;
  return 'Sin vigencia conocida';
}
const TONE = { valid: 'ok', expiring: 'warn', expired: 'danger', unknown: 'neutral', none: 'neutral' } as const;
function fielBadge(f: VaultCompany['fiel']) {
  if (f.state === 'valid') return 'FIEL vigente';
  if (f.state === 'expiring') return `FIEL vence en ${f.days} ${f.days === 1 ? 'día' : 'días'}`;
  if (f.state === 'expired') return 'FIEL vencida';
  if (f.state === 'unknown') return 'FIEL sin vigencia';
  return 'Sin FIEL';
}
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const VERB: Record<string, string> = { VER: 'vio', COPIAR: 'copió', USO_DECLARA: 'usó en Declara' };
const WHAT: Record<string, string> = {
  SAT_CIEC: 'la CIEC',
  IMSS_IDSE: 'IMSS',
  SIPARE: 'SIPARE',
  INFONAVIT: 'Infonavit',
  CORREO: 'el correo',
  OTRO: 'una contraseña',
  LLAVE: 'la llave de una firma',
};
function lastAccess(a: Summary['last_access']) {
  if (!a) return 'Sin accesos todavía';
  const at = new Date(a.at);
  const today = new Date().toDateString() === at.toDateString();
  const when = today
    ? 'Hoy ' + at.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })
    : at.toLocaleDateString('es-MX');
  return `${when} · ${VERB[a.kind] || a.kind.toLowerCase()} ${a.what ? WHAT[a.what] || '' : 'la FIEL'}`.trim();
}

/** A small menu button (⋯, «Agregar»): real buttons, closes with Escape or a click outside. */
function Menu({
  label,
  children,
  items,
  className = stitchButton,
}: {
  label: string;
  children: ReactNode;
  items: { label: string; onSelect: () => void; danger?: boolean }[];
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', away);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);
  if (!items.length) return null;
  return (
    <div className="v2-menu" ref={box}>
      <button
        type="button"
        className={className}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {children}
      </button>
      {open && (
        <ul role="menu" className="v2-menu-list">
          {items.map((i) => (
            <li key={i.label} role="none">
              <button
                type="button"
                role="menuitem"
                className={i.danger ? 'is-danger' : ''}
                onClick={() => {
                  setOpen(false);
                  i.onSelect();
                }}
              >
                {i.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type LogRow = { id: string; actor_id: string; action: string; record_id: string | null; created_at: string };
const LOG_ACTIONS: Record<string, string> = {
  secret_revealed: 'Vio una contraseña',
  secret_copied: 'Copió una contraseña',
  reveal_blocked: 'Intento de ver o copiar con la bóveda bloqueada',
  reauth_confirmed: 'Confirmó su contraseña',
  reauth_failed: 'Contraseña de confirmación incorrecta',
  reauth_required: 'Se pidió confirmar la contraseña',
  vault_setup: 'Creó la bóveda',
  vault_unlock_failed: 'Intento fallido de desbloqueo',
  vault_locked: 'Bloqueó la bóveda',
  vault_password_changed: 'Cambió su contraseña maestra',
  vault_recovery_regenerated: 'Generó un código de recuperación nuevo',
  vault_settings_changed: 'Cambió el autobloqueo',
  vault_member_added: 'Dio acceso a la bóveda',
  vault_member_removed: 'Quitó el acceso a la bóveda',
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
  standalone = false,
}: {
  companyId?: string;
  notify: (s: string) => void;
  /** Names of the people the page already knows (id → name), to show in the log instead of internal ids. */
  users?: Record<string, string>;
  /** The module page (/gestor-contrasenas) draws its own header with the actions of the design. */
  standalone?: boolean;
}) {
  const vault = useVault();
  const [data, setData] = useState<Vault | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [regime, setRegime] = useState('');
  const [chip, setChip] = useState('all');
  const [reload, setReload] = useState(0);
  const [shown, setShown] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<Item | 'new' | null>(null);
  // Fase 3: «Agregar FIEL o CSD» (company and class preselected from a signature card, if any).
  const [signing, setSigning] = useState<null | { company?: string; klass: SignatureClass }>(null);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [generator, setGenerator] = useState(false);
  const [history, setHistory] = useState<string | null>(null);
  const [selected, setSelected] = useState('');
  const [tab, setTab] = useState<'credentials' | 'log'>('credentials');
  const [log, setLog] = useState<LogRow[] | null>(null);
  const timers = useRef<Record<string, number>>({});
  useEffect(() => {
    const abort = new AbortController();
    const q = new URLSearchParams(companyId ? { company_id: companyId } : {});
    api<Vault>('/credentials/vault?' + q, 'GET', undefined, abort.signal)
      .then((d) => {
        setData(d);
        setError('');
      })
      .catch((e) => {
        if (abort.signal.aborted) return;
        if (isLockedError(e)) vault.locked();
        else setError(e.message);
      });
    return () => abort.abort();
  }, [companyId, reload, vault]);
  useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), []);

  /** Runs `action`; when the vault locked itself meanwhile, the screen goes back to the lock card. */
  async function withReauth(action: () => Promise<void>) {
    try {
      await action();
    } catch (e) {
      if (isLockedError(e)) vault.locked();
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
  // A password shown hides itself again after 20 seconds.
  async function reveal(cid: string, id: string) {
    if (shown[id]) return hide(id);
    await withReauth(async () => {
      const r = await api<{ secret: string; expires_in: number }>(
        `/credentials/companies/${cid}/secrets/${id}/reveal`,
        'POST',
        { action: 'view' },
      );
      setShown((old) => ({ ...old, [id]: r.secret }));
      clearTimeout(timers.current[id]);
      timers.current[id] = window.setTimeout(() => hide(id), r.expires_in * 1000);
    });
  }
  // On copy, the clipboard is cleared after 30 seconds (as far as the browser allows).
  async function copy(cid: string, id: string) {
    await withReauth(async () => {
      const r = await api<{ secret: string }>(`/credentials/companies/${cid}/secrets/${id}/reveal`, 'POST', {
        action: 'copy',
      });
      await navigator.clipboard.writeText(r.secret);
      notify('Contraseña copiada; el portapapeles se limpia en 30 segundos.');
      window.setTimeout(() => {
        navigator.clipboard.writeText('').catch(() => undefined);
      }, 30000);
    });
  }
  async function autofill(item: Item) {
    if (!extensionReady()) {
      notify('Instala la extensión de ContaSuite en Chrome o Edge para entrar al portal del SAT con autocompletado.');
      return;
    }
    await withReauth(async () => {
      const r = await api<{ ticket: string }>(
        `/credentials/companies/${item.company_id}/secrets/${item.id}/ticket`,
        'POST',
        { purpose: 'sat_password' },
      );
      notify(
        await sendToExtension({
          type: 'autofill',
          purpose: 'sat_password',
          ticket: r.ticket,
          server: window.location.origin,
        }),
      );
    });
  }
  async function archive(item: Item) {
    if (!confirm(`¿Archivar «${item.label || item.portal}» de ${item.company_name}? Queda en el historial.`)) return;
    await withReauth(async () => {
      await api(`/credentials/companies/${item.company_id}/secrets/${item.id}?revision=${item.revision}`, 'DELETE');
      setReload((n) => n + 1);
    });
  }
  async function removeCertificate(c: Cert) {
    if (!confirm(`¿Eliminar «${CLASS_LABELS[c.cert_class]}»? Sale de las tarjetas y queda en el historial.`)) return;
    await withReauth(async () => {
      await api(`/credentials/companies/${c.company_id}/certificates/${c.id}`, 'DELETE');
      setReload((n) => n + 1);
      notify('Certificado enviado al historial.');
    });
  }
  async function openLog() {
    setTab('log');
    setLog(null);
    try {
      setLog(await api<LogRow[]>(`/credentials/companies/${current}/history`));
    } catch (e) {
      setLog([]);
      if (isLockedError(e)) vault.locked();
      else notify((e as Error).message);
    }
  }

  const admin = vault.isAdmin || !!data?.can_export;
  const items = data?.items || [];
  const regimes = [...new Set((data?.companies || []).map((c) => c.regime).filter(Boolean))].sort();
  const q = query.trim().toLowerCase();
  const companies = (data?.companies || []).filter(
    (c) => (!q || (c.name + ' ' + c.rfc).toLowerCase().includes(q)) && (!regime || c.regime === regime),
  );
  const current = companyId || (companies.some((c) => c.id === selected) ? selected : companies[0]?.id) || '';
  const company = data?.companies.find((c) => c.id === current);
  const certs = (data?.certificates || []).filter((c) => c.company_id === current);
  const activeCerts = certs.filter(
    (c) =>
      c.active &&
      (chip === 'all' || (chip === 'FIEL' && c.cert_class !== 'CSD') || (chip === 'CSD' && c.cert_class === 'CSD')),
  );
  const mine = items.filter((i) => i.company_id === current && kindOf(i) !== 'LLAVE');
  const groups = KINDS.map(([kind, label]) => ({ kind, label, rows: mine.filter((i) => kindOf(i) === kind) })).filter(
    (g) => (chip === 'all' ? g.rows.length > 0 : g.kind === chip),
  );
  const showSignatures = chip === 'all' || chip === 'FIEL' || chip === 'CSD';
  const s = data?.summary;
  const addMenu = admin
    ? [
        { label: 'Contraseña', onSelect: () => setEditing('new') },
        { label: 'FIEL o CSD', onSelect: () => setSigning({ company: current, klass: 'FIEL_EMPRESA' }) },
      ]
    : [];
  const moreMenu = [
    ...(admin
      ? [
          { label: 'Exportar', onSelect: () => setExporting(true) },
          { label: 'Descargar plantilla de Excel', onSelect: () => downloadTemplate(notify) },
        ]
      : []),
    { label: 'Generar contraseña', onSelect: () => setGenerator(true) },
  ];
  const actions = (
    <div className="v2-vault-actions">
      <VaultTimer />
      <LockNow />
      {admin && (
        <button className={stitchButton} onClick={() => setImporting(true)}>
          <Upload size={16} aria-hidden /> Importar
        </button>
      )}
      <Menu label="Agregar" items={addMenu} className={stitchPrimary}>
        <Plus size={16} aria-hidden /> Agregar
      </Menu>
      <Menu
        label="Más opciones: exportar, descargar plantilla, generar contraseña"
        items={moreMenu}
        className={stitchButton + ' icon-only'}
      >
        <MoreHorizontal size={18} aria-hidden />
      </Menu>
    </div>
  );
  const secret = (cid: string, id: string, label: string) => (
    <div className="v2-vault-secret">
      <span className="v2-vault-dots" aria-live="polite">
        {shown[id] ?? '••••••••••'}
      </span>
      <button
        className={stitchButton + ' icon-only'}
        aria-label={(shown[id] ? 'Ocultar' : 'Mostrar') + ' ' + label}
        onClick={() => reveal(cid, id)}
      >
        {shown[id] ? <EyeOff size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
      </button>
      <button className={stitchButton + ' icon-only'} aria-label={'Copiar ' + label} onClick={() => copy(cid, id)}>
        <Copy size={16} aria-hidden />
      </button>
    </div>
  );

  return (
    <section className="v11-vault v2-vault">
      {standalone ? (
        <header className="v2-vault-header">
          <div>
            <span className="v2-eyebrow">MÓDULO</span>
            <h1>Gestor de contraseñas</h1>
            <p className="muted">
              Contraseñas del SAT y archivos FIEL de cada empresa, cifrados y protegidos con tu contraseña maestra.
            </p>
          </div>
          {actions}
        </header>
      ) : (
        actions
      )}
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {s && (
        <div className="v2-vault-kpis" role="group" aria-label="Revisión de seguridad">
          <div>
            <span>Contraseñas guardadas</span>
            <strong>{s.passwords}</strong>
          </div>
          <div>
            <span>FIEL y CSD guardados</span>
            <strong>
              {s.certificates}
              {s.expiring > 0 && (
                <small className="is-warn"> · {plural(s.expiring, 'vence pronto', 'vencen pronto')}</small>
              )}
              {s.expired > 0 && <small className="is-danger"> · {plural(s.expired, 'vencido', 'vencidos')}</small>}
            </strong>
          </div>
          <div>
            <span>Débiles o repetidas</span>
            <strong className={s.weak_or_repeated ? 'is-warn' : 'is-ok'}>{s.weak_or_repeated}</strong>
            <small className="muted">Revisión local, sin enviar nada fuera</small>
          </div>
          <div>
            <span>Último acceso registrado</span>
            <strong className="is-text">{lastAccess(s.last_access)}</strong>
          </div>
        </div>
      )}
      <div className={'v2-vault-layout' + (companyId ? ' is-single' : '')}>
        {!companyId && (
          <aside className="v2-vault-companies" aria-label="Empresas del gestor">
            <label className="v2-search">
              <Search size={16} aria-hidden />
              <input
                type="search"
                aria-label="Buscar empresa o RFC"
                placeholder="Buscar empresa o RFC"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            {regimes.length > 1 && (
              <select aria-label="Filtrar por régimen" value={regime} onChange={(e) => setRegime(e.target.value)}>
                <option value="">Todos los regímenes</option>
                {regimes.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            )}
            <ul>
              {companies.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    aria-pressed={c.id === current}
                    onClick={() => {
                      setSelected(c.id);
                      setTab('credentials');
                      setHistory(null);
                    }}
                  >
                    <strong>{c.name}</strong>
                    <span className="rfc">{c.rfc}</span>
                    <span className="v2-vault-badges">
                      <span className={'v2-vpill is-' + TONE[c.fiel.state]}>{fielBadge(c.fiel)}</span>
                      <span className="v2-vpill is-neutral">
                        {plural(c.certificate_count, 'certificado', 'certificados')} ·{' '}
                        {plural(c.password_count, 'contraseña', 'contraseñas')}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
              {data && !companies.length && <li className="muted">Sin empresas con estos filtros.</li>}
            </ul>
          </aside>
        )}
        <div className="v2-vault-detail">
          {company && (
            <header className="v2-vault-company">
              <div>
                <h2>{company.name}</h2>
                <span className="rfc">
                  {company.rfc} · Persona {company.person_type.toLowerCase()}
                </span>
              </div>
              <div className="v2-segmented" role="group" aria-label="Sección del gestor">
                <button type="button" aria-pressed={tab === 'credentials'} onClick={() => setTab('credentials')}>
                  <KeyRound size={16} aria-hidden /> Credenciales
                </button>
                <button type="button" aria-pressed={tab === 'log'} onClick={openLog}>
                  <History size={16} aria-hidden /> Bitácora de accesos
                </button>
              </div>
            </header>
          )}
          {tab === 'credentials' && company && (
            <>
              <div className="v2-chips" role="group" aria-label="Filtrar por tipo">
                {CHIPS.map(([id, label]) => (
                  <button key={id} type="button" aria-pressed={chip === id} onClick={() => setChip(id)}>
                    {label}
                  </button>
                ))}
              </div>
              {showSignatures && (
                <section className="v2-vault-section" aria-labelledby="vault-signatures">
                  <h3 id="vault-signatures">Firmas y certificados</h3>
                  {activeCerts.length ? (
                    <div className="v2-cert-cards">
                      {activeCerts.map((c) => {
                        const old = certs.filter((x) => !x.active && x.cert_class === c.cert_class);
                        const title = CLASS_LABELS[c.cert_class];
                        return (
                          <article key={c.id} className="v2-cert-card">
                            <header>
                              <div>
                                <h4>{title}</h4>
                                <small className="muted">
                                  {[c.holder_name, c.holder_rfc, c.cert_class === 'CSD' ? c.branch : null]
                                    .filter(Boolean)
                                    .join(' · ') || company.name}
                                </small>
                              </div>
                              {c.cert_class === 'FIEL_REPRESENTANTE' && (
                                <span className="v2-tag-rep">REPRESENTANTE</span>
                              )}
                            </header>
                            <p className={'v2-cert-validity is-' + (c.incomplete ? 'warn' : TONE[c.validity])}>
                              {validityText(c)}
                            </p>
                            {c.files.cer || c.files.key ? (
                              <small className="v2-cert-files">
                                {[c.files.cer, c.files.key].filter(Boolean).join(' · ')}
                              </small>
                            ) : (
                              admin && (
                                <button
                                  className={stitchButton}
                                  onClick={() => setSigning({ company: c.company_id, klass: c.cert_class })}
                                >
                                  <FileKey2 size={16} aria-hidden /> Subir .cer y .key
                                </button>
                              )
                            )}
                            {c.key_password_id && (
                              <div className="v2-cert-secret">
                                {secret(c.company_id, c.key_password_id, 'contraseña de la llave de ' + title)}
                                <Menu
                                  label={'Más acciones de ' + title}
                                  className={stitchButton + ' icon-only'}
                                  items={[
                                    ...(admin
                                      ? [
                                          {
                                            label: 'Reemplazar',
                                            onSelect: () => setSigning({ company: c.company_id, klass: c.cert_class }),
                                          },
                                        ]
                                      : []),
                                    {
                                      label: history === c.id ? 'Ocultar historial' : 'Ver historial',
                                      onSelect: () => setHistory(history === c.id ? null : c.id),
                                    },
                                    ...(admin
                                      ? [{ label: 'Eliminar', danger: true, onSelect: () => removeCertificate(c) }]
                                      : []),
                                  ]}
                                >
                                  <MoreVertical size={16} aria-hidden />
                                </Menu>
                              </div>
                            )}
                            {history === c.id && (
                              <ul className="v2-cert-history" aria-label={'Historial de ' + title}>
                                {old.map((o) => (
                                  <li key={o.id}>
                                    <span className="rfc">{o.number || 'Sin número'}</span> · {validityText(o)}
                                  </li>
                                ))}
                                {!old.length && <li className="muted">Sin certificados anteriores.</li>}
                              </ul>
                            )}
                          </article>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="v2-empty muted">
                      Sin FIEL ni sello digital guardados.{' '}
                      {admin && (
                        <button
                          className="v2-link-button"
                          onClick={() => setSigning({ company: current, klass: 'FIEL_EMPRESA' })}
                        >
                          Agregar FIEL o CSD
                        </button>
                      )}
                    </p>
                  )}
                  <p className="muted small">
                    Los .cer y .key no se descargan. Declara usará la FIEL de la empresa para «Acceso con e.firma» del
                    SAT.
                  </p>
                </section>
              )}
              {(chip === 'all' || groups.length > 0) && chip !== 'FIEL' && chip !== 'CSD' && (
                <section className="v2-vault-section" aria-labelledby="vault-passwords">
                  <div className="v2-vault-section-head">
                    <h3 id="vault-passwords">Contraseñas por tipo</h3>
                  </div>
                  {groups.map((g) => (
                    <div key={g.kind} className="v2-kind-group">
                      <h4>
                        {g.label} <span className="muted">{g.rows.length}</span>
                      </h4>
                      {g.rows.length ? (
                        <ul>
                          {g.rows.map((i) => {
                            const st = status(i);
                            const name = i.label && i.label !== 'Acceso' ? i.label : i.portal;
                            return (
                              <li key={i.id}>
                                <strong>{name}</strong>
                                <span className="rfc">{i.username || <span className="muted">Sin usuario</span>}</span>
                                {secret(i.company_id, i.id, 'contraseña de ' + name)}
                                <span className={'v2-vpill is-' + st.tone}>{st.label}</span>
                                <span className="v2-kind-actions">
                                  {i.service_id === 'sat_password' && (
                                    <button
                                      className={stitchButton + ' icon-only'}
                                      aria-label="Entrar al SAT con la extensión"
                                      title="Abre el portal del SAT y llena el acceso con la extensión de ContaSuite"
                                      onClick={() => autofill(i)}
                                    >
                                      <ExternalLink size={16} aria-hidden />
                                    </button>
                                  )}
                                  <Menu
                                    label={'Más acciones de ' + name}
                                    className={stitchButton + ' icon-only'}
                                    items={
                                      i.can_modify
                                        ? [
                                            { label: 'Editar', onSelect: () => setEditing(i) },
                                            { label: 'Archivar', danger: true, onSelect: () => archive(i) },
                                          ]
                                        : []
                                    }
                                  >
                                    <MoreVertical size={16} aria-hidden />
                                  </Menu>
                                </span>
                              </li>
                            );
                          })}
                        </ul>
                      ) : (
                        <p className="muted small">Sin contraseñas de este tipo.</p>
                      )}
                    </div>
                  ))}
                  {admin && (
                    <button className="v2-add-password" onClick={() => setEditing('new')}>
                      <Plus size={16} aria-hidden /> Agregar contraseña
                    </button>
                  )}
                </section>
              )}
              <p className="muted small v2-vault-note">
                <Clock size={14} aria-hidden /> Ver, copiar o usar la FIEL queda registrado en la Bitácora de accesos
                con usuario, fecha y acción.
              </p>
            </>
          )}
          {tab === 'log' && company && (
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
                      <th scope="col">Recurso</th>
                    </tr>
                  </thead>
                  <tbody>
                    {log.map((r) => (
                      <tr key={r.id}>
                        <td>{new Date(r.created_at).toLocaleString('es-MX')}</td>
                        <td>{users[r.actor_id] || r.actor_id}</td>
                        <td>{LOG_ACTIONS[r.action] || r.action}</td>
                        <td>
                          {items.find((i) => i.id === r.record_id)?.label ||
                            (certs.find((c) => c.id === r.record_id) &&
                              CLASS_LABELS[certs.find((c) => c.id === r.record_id)!.cert_class]) ||
                            '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted">Sin movimientos registrados.</p>
              )}
              <p className="muted small">
                {admin ? 'Cada consulta de esta bitácora también queda registrada.' : 'Sólo ves tus propias acciones.'}
              </p>
            </div>
          )}
          {data && !company && <p className="v2-empty muted">No hay empresas para mostrar.</p>}
        </div>
      </div>
      {editing && data && (
        <CredentialForm
          item={editing === 'new' ? null : editing}
          companyId={companyId || current}
          vault={data}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setReload((n) => n + 1);
            notify('Credencial guardada cifrada.');
          }}
        />
      )}
      {signing && data && (
        <AddSignature
          companies={data.companies}
          companyId={companyId || signing.company}
          initialClass={signing.klass}
          onClose={() => setSigning(null)}
          onSaved={(message) => {
            setSigning(null);
            setReload((n) => n + 1);
            notify(message);
          }}
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
          onLocked={vault.locked}
          notify={notify}
        />
      )}
    </section>
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
