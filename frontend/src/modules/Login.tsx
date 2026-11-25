import { useEffect, useState, type FormEvent } from 'react';
import { api } from '../api';
import { Field, Logo } from '../components/ui';
import { stitchPrimary } from '../components/stitch';
import { AlertCircle, Eye, EyeOff } from 'lucide-react';

export default function Login({ onAuthenticated }: { onAuthenticated: () => Promise<void> }) {
  const [initialized, setInitialized] = useState<boolean | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [key, setKey] = useState('');
  const [display, setDisplay] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  // Rediseño v2: show the typed password on request (named «Mostrar»/«Ocultar» so the field keeps its label).
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const c = new AbortController();
    api<{ initialized: boolean }>('/auth/status', 'GET', undefined, c.signal)
      .then((s) => setInitialized(s.initialized))
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      });
    return () => c.abort();
  }, []);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (!initialized) {
        await api('/auth/bootstrap', 'POST', { username, password, display_name: display }, undefined, {
          Authorization: 'Bearer ' + key.trim(),
        });
        setInitialized(true);
        setKey('');
      }
      await api('/auth/login', 'POST', { username, password });
      sessionStorage.removeItem('contasuite-token');
      setPassword('');
      await onAuthenticated();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-page stitch-live-module">
      <form className="card login-card" onSubmit={submit}>
        <Logo size={56} />
        <h1>ContaSuite</h1>
        <p>{initialized === false ? 'Crea la cuenta administradora del despacho.' : 'Inicia sesión con tu cuenta.'}</p>
        {initialized === null ? (
          <p role="status">Consultando acceso…</p>
        ) : (
          <>
            {!initialized && (
              <>
                <Field label="Clave de instalación">
                  <input
                    type="password"
                    required
                    autoComplete="off"
                    value={key}
                    onChange={(e) => setKey(e.target.value)}
                  />
                </Field>
                <Field label="Nombre">
                  <input
                    required
                    maxLength={100}
                    autoComplete="name"
                    value={display}
                    onChange={(e) => setDisplay(e.target.value)}
                  />
                </Field>
              </>
            )}
            <Field label="Usuario">
              <input
                autoFocus
                required
                minLength={3}
                maxLength={64}
                pattern="[a-zA-Z0-9_.\-]+"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </Field>
            <Field label="Contraseña">
              <>
                <input
                  type={visible ? 'text' : 'password'}
                  className="login-password"
                  required
                  minLength={initialized ? 1 : 12}
                  maxLength={128}
                  autoComplete={initialized ? 'current-password' : 'new-password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="login-reveal"
                  aria-label={visible ? 'Ocultar' : 'Mostrar'}
                  aria-pressed={visible}
                  title={visible ? 'Ocultar lo escrito' : 'Mostrar lo escrito'}
                  onClick={() => setVisible((v) => !v)}
                >
                  {visible ? <EyeOff size={18} aria-hidden /> : <Eye size={18} aria-hidden />}
                </button>
              </>
            </Field>
            <button className={stitchPrimary} disabled={busy}>
              {busy ? 'Conectando…' : initialized ? 'Iniciar sesión' : 'Crear cuenta e ingresar'}
            </button>
            <small>
              {initialized
                ? 'La sesión caduca después de 30 minutos sin actividad. Las altas de usuario se gestionan con la administración del despacho.'
                : 'Usa al menos 12 caracteres. La clave de instalación dejará de dar acceso al crear esta cuenta.'}
            </small>
          </>
        )}
        {error && (
          <p className="login-error" role="alert">
            <AlertCircle size={16} aria-hidden /> {error}
          </p>
        )}
      </form>
      <footer className="login-footer">ContaSuite · Plataforma fiscal para despachos contables</footer>
    </div>
  );
}
