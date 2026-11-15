import { useEffect, useState } from 'react';
import { api, dateLabel } from '../api';
import { Badge } from '../components/ui';
import { stitchButton, stitchPrimary } from '../components/stitch';

type Link = {
  id: string;
  agent_id: string;
  machine: string;
  user: string | null;
  last_seen: string | null;
  online: boolean;
  revoked_at: string | null;
  revoked_reason: string | null;
  restart_requested: boolean;
};

/** Administrators: folders the agents may read, and every linked agent with revoke / restart (Bloque 4). */
export default function AgentAdmin({ notify }: { notify: (m: string) => void }) {
  const [links, setLinks] = useState<Link[] | null>(null);
  const [roots, setRoots] = useState('');
  const [saved, setSaved] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    api<{ links: Link[]; roots: string[] }>('/agent-links', 'GET', undefined, c.signal)
      .then((d) => {
        setLinks(d.links);
        setRoots(d.roots.join('\n'));
        setSaved(d.roots.join('\n'));
      })
      .catch((e) => {
        if (!c.signal.aborted) setError((e as Error).message);
      });
    return () => c.abort();
  }, [reload]);
  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError('');
    try {
      await action();
      notify(message);
      setReload((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const active = (links || []).filter((l) => !l.revoked_at);
  const ended = (links || []).filter((l) => l.revoked_at).slice(0, 10);
  return (
    <div className="agent-admin">
      <p className="muted">
        Cada usuario vincula el agente de su equipo al iniciar sesión en ContaSuite; el vínculo termina al cerrar o
        expirar su sesión. El agente sólo lee carpetas dentro de las rutas autorizadas aquí y de empresas a las que ese
        usuario tiene acceso.
      </p>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      <label className="field">
        <span>Carpetas autorizadas (una por línea; rutas absolutas como C:\Empresas o \\servidor\empresas)</span>
        <textarea rows={4} value={roots} disabled={busy} onChange={(e) => setRoots(e.target.value)} />
      </label>
      <button
        className={stitchPrimary}
        disabled={busy || roots === saved}
        onClick={() =>
          void run(
            () =>
              api('/agent-links/roots', 'PUT', {
                paths: roots
                  .split('\n')
                  .map((r) => r.trim())
                  .filter(Boolean),
              }),
            'Carpetas autorizadas actualizadas.',
          )
        }
      >
        Guardar carpetas autorizadas
      </button>
      <h4>Agentes vinculados</h4>
      {links === null ? (
        <p role="status">Consultando agentes…</p>
      ) : active.length === 0 ? (
        <p className="muted">Ningún agente vinculado ahora.</p>
      ) : (
        active.map((l) => (
          <div className="agent-line" key={l.id}>
            <div>
              <strong>{l.user || 'Usuario'}</strong>
              <small>
                {l.machine || l.agent_id} · {l.last_seen ? 'visto ' + dateLabel(l.last_seen) : 'sin contacto'}
                {l.restart_requested && ' · reinicio pendiente'}
              </small>
            </div>
            <Badge tone={l.online ? 'green' : 'neutral'}>{l.online ? 'Conectado' : 'Sin conexión'}</Badge>
            <button
              className={stitchButton}
              disabled={busy || l.restart_requested}
              onClick={() => void run(() => api('/agent-links/' + l.id + '/restart', 'POST'), 'Reinicio solicitado.')}
            >
              Reiniciar
            </button>
            <button
              className={stitchButton}
              disabled={busy}
              onClick={() =>
                window.confirm('¿Revocar el vínculo de este agente? El usuario deberá iniciar sesión de nuevo.') &&
                void run(() => api('/agent-links/' + l.id + '/revoke', 'POST'), 'Vínculo revocado.')
              }
            >
              Revocar
            </button>
          </div>
        ))
      )}
      {ended.length > 0 && (
        <details>
          <summary>Vínculos terminados recientes ({ended.length})</summary>
          {ended.map((l) => (
            <p key={l.id} className="muted">
              {l.user || 'Usuario'} · {l.machine || l.agent_id} · {l.revoked_reason || 'Terminado'}
            </p>
          ))}
        </details>
      )}
    </div>
  );
}
