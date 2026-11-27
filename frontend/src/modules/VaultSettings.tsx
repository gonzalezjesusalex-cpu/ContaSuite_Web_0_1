import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { KeyRound, Timer, UserPlus, Users } from 'lucide-react';
import { api } from '../api';
import { Field } from '../components/ui';
import { stitchButton, stitchCard, stitchDanger, stitchPrimary } from '../components/stitch';
import VaultGate, { isLockedError, useVault } from './VaultGate';
import './v11.css';

/** Configuración › Bóveda de contraseñas (renovación del gestor, fase 5; administrators): auto-lock minutes,
 *  people with their own master password, and a new recovery code. Everything here needs the vault unlocked. */
type Member = { user_id: string; name: string; pending: boolean; since: string };
type Account = { id: string; display_name: string; username: string; enabled: boolean };

export default function VaultSettings({ notify }: { notify: (s: string) => void }) {
  return (
    <VaultGate>
      <VaultSettingsPanel notify={notify} />
    </VaultGate>
  );
}

function VaultSettingsPanel({ notify }: { notify: (s: string) => void }) {
  const vault = useVault();
  const [minutes, setMinutes] = useState(5);
  const [members, setMembers] = useState<Member[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [chosen, setChosen] = useState('');
  const [code, setCode] = useState<{ title: string; value: string } | null>(null);
  const [master, setMaster] = useState('');
  const [error, setError] = useState('');
  const fail = useCallback(
    (e: unknown) => {
      if (isLockedError(e)) vault.locked();
      else setError((e as Error).message);
    },
    [vault],
  );
  const load = useCallback(async () => {
    try {
      const [state, list, users] = await Promise.all([
        api<{ auto_lock_minutes: number }>('/credentials/vault/state'),
        api<Member[]>('/credentials/vault/members'),
        api<Account[]>('/auth/users').catch(() => [] as Account[]),
      ]);
      setMinutes(state.auto_lock_minutes);
      setMembers(list);
      setAccounts(users.filter((u) => u.enabled));
      setError('');
    } catch (e) {
      fail(e);
    }
  }, [fail]);
  useEffect(() => {
    load();
  }, [load]);

  async function saveMinutes(e: FormEvent) {
    e.preventDefault();
    try {
      await api('/credentials/vault/settings', 'PUT', { auto_lock_minutes: minutes });
      notify(`La bóveda se bloqueará tras ${minutes} minutos sin uso.`);
    } catch (err) {
      fail(err);
    }
  }
  async function add(e: FormEvent) {
    e.preventDefault();
    try {
      const r = await api<{ temporary_code: string }>('/credentials/vault/members', 'POST', { user_id: chosen });
      const who = accounts.find((a) => a.id === chosen)?.display_name || 'la persona';
      setCode({ title: `Código temporal de ${who}`, value: r.temporary_code });
      setChosen('');
      load();
    } catch (err) {
      fail(err);
    }
  }
  async function remove(m: Member) {
    if (!confirm(`¿Quitar a ${m.name} el acceso a la bóveda? Si la tiene abierta, se bloquea en ese momento.`)) return;
    try {
      await api(`/credentials/vault/members/${m.user_id}`, 'DELETE');
      load();
    } catch (err) {
      fail(err);
    }
  }
  async function recovery(e: FormEvent) {
    e.preventDefault();
    try {
      const r = await api<{ recovery_code: string }>('/credentials/vault/recovery', 'POST', { password: master });
      setMaster('');
      setCode({ title: 'Código de recuperación nuevo', value: r.recovery_code });
    } catch (err) {
      setMaster('');
      fail(err);
    }
  }
  const candidates = accounts.filter((a) => !members.some((m) => m.user_id === a.id));

  return (
    <section className={stitchCard + ' padded v2-vault-settings'} aria-labelledby="vault-settings-title">
      <h2 id="vault-settings-title">Bóveda de contraseñas</h2>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {code && (
        <div className="v2-vault-code" role="status">
          <h3>{code.title}</h3>
          <p className="v2-vault-recovery" aria-label={code.title}>
            {code.value}
          </p>
          <p className="muted small">
            Se muestra sólo esta vez. Entrégalo en persona o imprímelo; no lo envíes por correo ni por chat.
          </p>
          <button className={stitchButton} onClick={() => setCode(null)}>
            Ya lo guardé
          </button>
        </div>
      )}
      <form className="v2-vault-settings-block" onSubmit={saveMinutes}>
        <h3>
          <Timer size={16} aria-hidden /> Bloqueo automático
        </h3>
        <Field label="Minutos sin uso antes de bloquear">
          <input type="number" min={1} max={60} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} />
        </Field>
        <button className={stitchPrimary} disabled={minutes < 1 || minutes > 60}>
          Guardar
        </button>
      </form>
      <div className="v2-vault-settings-block">
        <h3>
          <Users size={16} aria-hidden /> Personas con acceso
        </h3>
        <p className="muted small">
          Cada persona tiene su propia contraseña maestra. Puede ver y copiar contraseñas; sólo los administradores
          agregan, editan, importan o exportan.
        </p>
        <ul className="v2-vault-members">
          {members.map((m) => (
            <li key={m.user_id}>
              <span>
                <strong>{m.name}</strong>
                {m.pending && <span className="v2-vpill is-warn">Pendiente de elegir su contraseña</span>}
              </span>
              <button className={stitchDanger} onClick={() => remove(m)} aria-label={'Quitar acceso a ' + m.name}>
                Quitar acceso
              </button>
            </li>
          ))}
        </ul>
        {candidates.length > 0 && (
          <form onSubmit={add} className="v2-vault-settings-row">
            <Field label="Dar acceso a">
              <select value={chosen} onChange={(e) => setChosen(e.target.value)} required>
                <option value="">Elige una persona…</option>
                {candidates.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.display_name} ({a.username})
                  </option>
                ))}
              </select>
            </Field>
            <button className={stitchButton} disabled={!chosen}>
              <UserPlus size={16} aria-hidden /> Dar acceso
            </button>
          </form>
        )}
      </div>
      <form className="v2-vault-settings-block" onSubmit={recovery}>
        <h3>
          <KeyRound size={16} aria-hidden /> Código de recuperación
        </h3>
        <p className="muted small">
          Genera uno nuevo si el anterior se perdió o ya se usó. El anterior deja de funcionar.
        </p>
        <Field label="Tu contraseña maestra">
          <input
            type="password"
            autoComplete="current-password"
            value={master}
            onChange={(e) => setMaster(e.target.value)}
          />
        </Field>
        <button className={stitchButton} disabled={!master}>
          Generar código nuevo
        </button>
      </form>
    </section>
  );
}
