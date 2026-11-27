import { useEffect, useState } from 'react';
import { AlertTriangle, FolderOpen, PlugZap, RefreshCw } from 'lucide-react';
import { api } from '../../api';
import { stitchButton, stitchCard, stitchPrimary } from '../../components/stitch';
import FolderPicker from './FolderPicker';
import { folderOp, lockText, waitJob, type CompanyFolder, type Probe } from './folderJobs';
import type { Run } from './model';

const ORIGIN_TEXT: Record<string, string> = {
  plantilla: 'plantilla de Configuración › Declara',
  red: 'red local (SMB)',
  equipo: 'este equipo',
};

function Light({ label, state, text }: { label: string; state: 'ok' | 'warn' | 'bad' | 'idle'; text: string }) {
  return (
    <li className={'declara-light ' + state}>
      <span className="declara-light-dot" aria-hidden="true" />
      <strong>{label}</strong>
      <small>{text}</small>
    </li>
  );
}

/** Paso 1 en modo carpeta: carpeta vinculada, prueba de conexión con semáforo y «Analizar carpeta». */
export default function FolderSource({
  companyId,
  companyName,
  year,
  shortName,
  ready,
  lastRun,
  backup,
  poll,
  onBackup,
  onPoll,
  onAnalyzed,
}: {
  companyId: string;
  companyName: string;
  year: number;
  shortName: string;
  ready: boolean;
  lastRun: Run | undefined;
  backup: boolean;
  poll: boolean;
  onBackup: (v: boolean) => void;
  onPoll: (v: boolean) => void;
  onAnalyzed: (runId: string) => void;
}) {
  const [info, setInfo] = useState<CompanyFolder | null>(null);
  const [path, setPath] = useState('');
  const [origin, setOrigin] = useState('');
  const [link, setLink] = useState(false);
  const [probe, setProbe] = useState<Probe | null>(null);
  const [picker, setPicker] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setProbe(null);
    api<CompanyFolder>(`/declara/companies/${encodeURIComponent(companyId)}/folder?year=${year}`)
      .then((f) => {
        if (!active) return;
        setInfo(f);
        setPath(f.ruta || '');
        setOrigin(f.origen || '');
        setLink(!f.vinculada && !!f.ruta);
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [companyId, year]);

  async function test() {
    setBusy('probar');
    setError('');
    try {
      setProbe(await folderOp<Probe>(companyId, 'probar', path));
    } catch (e) {
      setProbe(null);
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function analyze() {
    setBusy('analizar');
    setError('');
    try {
      const { job_id } = await api<{ job_id: string }>('/declara/folder/analyze', 'POST', {
        company_id: companyId,
        year,
        short_name: shortName,
        ruta: path,
        vincular: link,
        origen: origin === 'plantilla' ? 'plantilla' : path.startsWith('\\\\') ? 'red' : 'equipo',
      });
      const result = await waitJob<{ analisis_id: string }>(job_id, 15 * 60_000);
      onAnalyzed(result.analisis_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  const latency = probe?.latencia_ms;
  const lock = probe?.bloqueo;
  const known = lastRun?.folder_path?.toLowerCase() === path.toLowerCase() ? lastRun : undefined;
  return (
    <section className={stitchCard + ' padded declara-folder-card'}>
      <h2 className="declara-card-title">Carpeta vinculada</h2>
      {path ? (
        <>
          <p className="declara-folder-path">{path}</p>
          <p className="muted">
            Origen: {ORIGIN_TEXT[origin] || (path.startsWith('\\\\') ? ORIGIN_TEXT.red : ORIGIN_TEXT.equipo)}
            {info?.vinculada ? ` · vinculada a ${year}` : ''}
          </p>
        </>
      ) : (
        <p className="muted">
          Sin carpeta para {year}. Elige una o define la plantilla de ruta en Configuración › Declara.
        </p>
      )}
      <div className="actions">
        <button type="button" className={stitchButton} disabled={!!busy || !info} onClick={() => setPicker(true)}>
          <FolderOpen size={16} />
          Cambiar carpeta
        </button>
        <button type="button" className={stitchButton} disabled={!!busy || !path} onClick={test}>
          {busy === 'probar' ? <RefreshCw size={16} className="recopila-spinner" /> : <PlugZap size={16} />}
          Probar conexión
        </button>
      </div>
      <ul className="declara-lights" aria-label="Estado de la carpeta">
        <Light
          label="Lectura"
          state={!probe ? 'idle' : probe.lectura ? 'ok' : 'bad'}
          text={!probe ? 'Sin probar' : probe.lectura ? 'Correcta' : 'Sin acceso'}
        />
        <Light
          label="Escritura"
          state={!probe ? 'idle' : probe.escritura ? 'ok' : 'bad'}
          text={!probe ? 'Sin probar' : probe.escritura ? 'Correcta' : 'Sin permiso: no se podrá aplicar'}
        />
        <Light
          label="Latencia de red"
          state={latency == null ? 'idle' : latency < 300 ? 'ok' : latency < 1500 ? 'warn' : 'bad'}
          text={latency == null ? 'Sin probar' : `${latency} ms`}
        />
        <Light
          label="Bloqueo"
          state={!lock ? 'idle' : lock.estado === 'ajeno' ? 'bad' : 'ok'}
          text={lock ? lockText(lock) : 'Sin probar'}
        />
      </ul>
      <label className="declara-check">
        <input type="checkbox" checked={backup} onChange={(e) => onBackup(e.target.checked)} />
        Respaldar originales antes de renombrar
      </label>
      <label className="declara-check">
        <input type="checkbox" checked={poll} onChange={(e) => onPoll(e.target.checked)} />
        Revisar cambios cada 60 s
      </label>
      {known?.summary && typeof known.summary.archivos === 'number' && (
        <p className="muted">
          Hay índice: solo se leerán los PDF nuevos o modificados (último análisis: {known.summary.leidos} de{' '}
          {known.summary.archivos}).
        </p>
      )}
      <p className="declara-banner">
        <AlertTriangle size={16} aria-hidden="true" />
        Modo carpeta: los cambios se aplican directamente en la carpeta, con respaldo y registro para deshacerlos.
      </p>
      {error && <p className="declara-msg error">{error}</p>}
      <div className="actions">
        <button type="button" className={stitchPrimary} disabled={!ready || !path || !!busy} onClick={analyze}>
          {busy === 'analizar' ? <RefreshCw size={16} className="recopila-spinner" /> : <RefreshCw size={16} />}
          {busy === 'analizar' ? 'Analizando carpeta…' : 'Analizar carpeta'}
        </button>
      </div>
      {picker && info && (
        <FolderPicker
          companyId={companyId}
          companyName={companyName}
          year={year}
          info={{ ...info, ruta: path }}
          onClose={() => setPicker(false)}
          onChoose={(chosen, from, linkIt) => {
            setPath(chosen);
            setOrigin(from);
            setLink(linkIt);
            setProbe(null);
            setPicker(false);
          }}
        />
      )}
    </section>
  );
}
