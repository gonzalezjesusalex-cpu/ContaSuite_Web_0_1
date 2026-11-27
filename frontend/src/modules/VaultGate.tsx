import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import { KeyRound, Lock, LockOpen, Printer, ShieldCheck } from 'lucide-react';
import { api } from '../api';
import { Field } from '../components/ui';
import { stitchButton, stitchCard, stitchPrimary } from '../components/stitch';

/** Renovación del gestor, fase 1: the vault opens only with a master password (distinct from the login password).
 *  Nothing of the companies is requested while it is locked; the server keeps the data key in memory only. */
type VaultState = {
  configured: boolean;
  member: boolean;
  can_setup: boolean;
  unlocked: boolean;
  seconds_left: number;
  must_change: boolean;
  auto_lock_minutes: number;
  blocked_seconds: number;
  is_admin: boolean;
};

const MIN = 12;
/** Inside the gate: a request answered «bóveda bloqueada» (423) sends the screen back to the lock. Fase 5: the
 *  countdown and «Bloquear ahora» live in the module header (VaultTimer), so the context also carries them. */
type Gate = { locked: () => void; lockNow: () => void; seconds: number; isAdmin: boolean };
export const VaultContext = createContext<Gate>({
  locked: () => undefined,
  lockNow: () => undefined,
  seconds: 0,
  isAdmin: false,
});
export const useVault = () => useContext(VaultContext);
export const isLockedError = (e: unknown) => /bóveda está bloqueada/i.test((e as Error)?.message || '');

export function clock(seconds: number) {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export default function VaultGate({ children, header }: { children: ReactNode; header?: ReactNode }) {
  const [state, setState] = useState<VaultState | null>(null);
  const [error, setError] = useState('');
  const [recovery, setRecovery] = useState('');
  const load = useCallback(async () => {
    try {
      const s = await api<VaultState>('/credentials/vault/state');
      setState(s);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  const lockNow = useCallback(async () => {
    await api('/credentials/vault/lock', 'POST').catch(() => undefined);
    setRecovery('');
    await load();
  }, [load]);
  const seconds = state?.unlocked ? state.seconds_left : 0;
  const isAdmin = !!state?.is_admin;
  const context = useMemo(
    () => ({ locked: () => void load(), lockNow: () => void lockNow(), seconds, isAdmin }),
    [load, lockNow, seconds, isAdmin],
  );
  // «Bloqueado» of the design: the module header stays, the companies never appear.
  const locked = (card: ReactNode) => (
    <>
      {header}
      {card}
    </>
  );

  if (!state)
    return locked(
      error ? (
        <p role="alert" className="error-banner">
          {error}
        </p>
      ) : (
        <p role="status">Consultando la bóveda…</p>
      ),
    );
  if (recovery)
    return locked(
      <RecoveryCode
        code={recovery}
        onDone={() => {
          setRecovery('');
          load();
        }}
      />,
    );
  if (!state.configured)
    return locked(
      state.can_setup ? (
        <SetupWizard onCreated={(code) => setRecovery(code)} />
      ) : (
        <LockCard title="El gestor todavía no está listo">
          <p className="muted">Un administrador debe crear la contraseña maestra de la bóveda.</p>
        </LockCard>
      ),
    );
  if (!state.unlocked) return locked(<LockedCard state={state} onOpened={load} />);
  if (state.must_change) return locked(<NewPassword onDone={load} />);
  return <VaultContext.Provider value={context}>{children}</VaultContext.Provider>;
}

/** «Desbloqueado · se bloquea en m:ss»: its own state so the module does not re-render every second. */
export function VaultTimer() {
  const { seconds, locked: onExpired } = useVault();
  return <Countdown key={seconds} seconds={seconds} onExpired={onExpired} />;
}

function Countdown({ seconds, onExpired }: { seconds: number; onExpired: () => void }) {
  const [left, setLeft] = useState(seconds);
  const lastTouch = useRef(0);
  // Local countdown; at zero the server has already dropped the key, so the screen locks too.
  useEffect(() => {
    const t = window.setInterval(() => setLeft((n) => n - 1), 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (left <= 0) onExpired();
  }, [left, onExpired]);
  // Activity on the screen keeps it open (at most one ping every 20 s); it never opens a locked vault.
  useEffect(() => {
    const ping = () => {
      if (Date.now() - lastTouch.current < 20000) return;
      lastTouch.current = Date.now();
      api<VaultState>('/credentials/vault/touch', 'POST')
        .then((s) => (s.unlocked ? setLeft(s.seconds_left) : onExpired()))
        .catch(() => undefined);
    };
    window.addEventListener('pointerdown', ping);
    window.addEventListener('keydown', ping);
    return () => {
      window.removeEventListener('pointerdown', ping);
      window.removeEventListener('keydown', ping);
    };
  }, [onExpired]);
  return (
    <span className="v2-vault-timer" role="timer" aria-label={'Desbloqueado, se bloquea en ' + clock(left)}>
      <LockOpen size={16} aria-hidden /> Desbloqueado · se bloquea en {clock(left)}
    </span>
  );
}

/** «Bloquear ahora». */
export function LockNow() {
  const { lockNow } = useVault();
  return (
    <button className={stitchButton} onClick={lockNow}>
      <Lock size={16} aria-hidden /> Bloquear ahora
    </button>
  );
}

function LockCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={stitchCard + ' padded v2-vault-lock'} aria-labelledby="vault-lock-title">
      <span className="v2-vault-lock-icon" aria-hidden>
        <Lock size={28} />
      </span>
      <h2 id="vault-lock-title">{title}</h2>
      {children}
    </section>
  );
}

function LockedCard({ state, onOpened }: { state: VaultState; onOpened: () => void }) {
  const [password, setPassword] = useState('');
  const [useRecovery, setUseRecovery] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api('/credentials/vault/unlock', 'POST', useRecovery ? { recovery_code: password } : { password });
      setPassword('');
      onOpened();
    } catch (err) {
      setPassword('');
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!state.member)
    return (
      <LockCard title="La bóveda está bloqueada">
        <p className="muted">No tienes acceso a la bóveda. Pídelo a un administrador.</p>
      </LockCard>
    );
  return (
    <LockCard title="La bóveda está bloqueada">
      <p className="muted">
        {useRecovery
          ? 'Escribe el código de recuperación impreso. Después elegirás una contraseña maestra nueva.'
          : 'Escribe tu contraseña maestra. Es distinta de la contraseña con la que entras a ContaSuite.'}
      </p>
      <form onSubmit={submit} className="v2-vault-lock-form">
        <Field label={useRecovery ? 'Código de recuperación' : 'Contraseña maestra'}>
          <input
            type={useRecovery ? 'text' : 'password'}
            autoComplete={useRecovery ? 'off' : 'current-password'}
            autoFocus
            required
            spellCheck={false}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {(error || state.blocked_seconds > 0) && (
          <p role="alert" className="error-banner">
            {error || `Demasiados intentos. Espera ${clock(state.blocked_seconds)} para volver a intentar.`}
          </p>
        )}
        <button className={stitchPrimary} disabled={busy || !password}>
          <LockOpen size={16} aria-hidden /> Desbloquear
        </button>
        {state.is_admin && (
          <button
            type="button"
            className="v2-link-button"
            onClick={() => {
              setUseRecovery((v) => !v);
              setPassword('');
              setError('');
            }}
          >
            {useRecovery
              ? 'Usar la contraseña maestra'
              : '¿Olvidaste la contraseña maestra? Usa el código de recuperación'}
          </button>
        )}
      </form>
      <p className="muted small">
        Se bloquea sola tras {state.auto_lock_minutes} minutos sin uso. Cada intento queda en la bitácora.
      </p>
    </LockCard>
  );
}

function PasswordPair({
  password,
  confirm,
  setPassword,
  setConfirm,
}: {
  password: string;
  confirm: string;
  setPassword: (s: string) => void;
  setConfirm: (s: string) => void;
}) {
  return (
    <>
      <Field
        label="Contraseña maestra"
        error={password && password.length < MIN ? `Mínimo ${MIN} caracteres (llevas ${password.length}).` : undefined}
      >
        <input
          type="password"
          autoComplete="new-password"
          autoFocus
          required
          minLength={MIN}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      <Field label="Confirma la contraseña" error={confirm && confirm !== password ? 'No coincide.' : undefined}>
        <input
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </Field>
    </>
  );
}

function SetupWizard({ onCreated }: { onCreated: (code: string) => void }) {
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const r = await api<{ recovery_code: string }>('/credentials/vault/setup', 'POST', { password, confirm });
      setPassword('');
      setConfirm('');
      onCreated(r.recovery_code);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <LockCard title="Crea la contraseña maestra">
      <p className="muted">
        Protege todas las contraseñas y los archivos FIEL y CSD del despacho. Sin ella ni el código de recuperación, los
        datos no se pueden recuperar: nadie más la conoce, tampoco ContaSuite.
      </p>
      <form onSubmit={submit} className="v2-vault-lock-form">
        <PasswordPair password={password} confirm={confirm} setPassword={setPassword} setConfirm={setConfirm} />
        {error && (
          <p role="alert" className="error-banner">
            {error}
          </p>
        )}
        <button className={stitchPrimary} disabled={busy || password.length < MIN || password !== confirm}>
          <ShieldCheck size={16} aria-hidden /> {busy ? 'Creando la bóveda…' : 'Crear la bóveda'}
        </button>
      </form>
    </LockCard>
  );
}

function RecoveryCode({ code, onDone }: { code: string; onDone: () => void }) {
  const [saved, setSaved] = useState(false);
  return (
    <LockCard title="Guarda tu código de recuperación">
      <p className="muted">
        Es la única forma de abrir la bóveda si se olvida la contraseña maestra. Se muestra sólo esta vez: imprímelo y
        guárdalo en un lugar seguro, fuera de la computadora.
      </p>
      <p className="v2-vault-recovery" aria-label="Código de recuperación">
        {code}
      </p>
      <div className="actions">
        <button className={stitchButton} onClick={() => window.print()}>
          <Printer size={16} aria-hidden /> Imprimir
        </button>
      </div>
      <label className="check-option">
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} /> Ya lo imprimí o lo guardé
      </label>
      <button className={stitchPrimary} disabled={!saved} onClick={onDone}>
        <KeyRound size={16} aria-hidden /> Continuar al gestor
      </button>
    </LockCard>
  );
}

function NewPassword({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api('/credentials/vault/password', 'POST', { password, confirm });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <LockCard title="Elige tu contraseña maestra">
      <p className="muted">
        Entraste con un código temporal o de recuperación. Elige una contraseña maestra propia para seguir.
      </p>
      <form onSubmit={submit} className="v2-vault-lock-form">
        <PasswordPair password={password} confirm={confirm} setPassword={setPassword} setConfirm={setConfirm} />
        {error && (
          <p role="alert" className="error-banner">
            {error}
          </p>
        )}
        <button className={stitchPrimary} disabled={password.length < MIN || password !== confirm}>
          <ShieldCheck size={16} aria-hidden /> Guardar contraseña maestra
        </button>
      </form>
    </LockCard>
  );
}
