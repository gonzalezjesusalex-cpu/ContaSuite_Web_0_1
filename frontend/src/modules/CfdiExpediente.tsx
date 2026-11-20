import { useEffect, useState } from 'react';
import { api, dateLabel } from '../api';
import { Badge } from '../components/ui';
import { stitchButton, stitchCard, stitchPrimary } from '../components/stitch';
import type { State } from '../types';

export type ReviewRow = {
  path: string;
  name: string;
  ext: string;
  kind: string;
  period: string;
  uuid: string;
  fecha: string;
  emisor: string;
  receptor: string;
  incoherence: string[];
  pair: string;
  partner: string;
  warnings: string[];
};
export type SavedItem = {
  id: string;
  path: string;
  name: string;
  kind: string;
  state: string;
  reasons: string[];
  folder_period: string;
  xml_period: string | null;
  decided_by: string | null;
  decided_period: string | null;
};
export const INCOHERENCE: Record<string, string> = {
  xml_ilegible: 'XML ilegible',
  emisor_distinto: 'Emisor distinto a la empresa',
  receptor_distinto: 'Receptor distinto a la empresa',
  periodo_distinto: 'Fecha fuera del mes de la carpeta',
  pareja_bloqueada: 'Su pareja XML tiene una incoherencia',
  mismo_sha_otra_empresa: 'Mismo archivo ligado a otra empresa o a ninguna',
  uuid_contenido_distinto: 'Mismo UUID con contenido distinto',
};
export const OMITTED: Record<string, string> = {
  otro_rfc: 'Carpeta de otro RFC',
  mes_no_elegido: 'Mes no elegido',
  subcarpeta: 'Subcarpeta (no se recorre)',
  extension: 'Extensión no elegida',
  fuera_de_ruta: 'Fuera de la ruta Tipo/RFC/AAAA-MM',
};
const SAVE_STATE: Record<string, string> = {
  saved: 'Guardado',
  ya_registrado: 'Ya registrado',
  revision: 'En revisión',
  bloqueado: 'Bloqueado',
  descartado: 'Descartado',
};
type Counts = { nuevo: number; ya_registrado: number; revision: number; bloqueado: number };

/** Save the reviewed files into the expediente (5.5) and write them into the company folder with the agent (5.7). */
export default function CfdiExpediente({
  runId,
  companyId,
  state,
  items,
  companies,
  onChanged,
  notify,
  refresh,
}: {
  runId: string;
  companyId: string | null;
  state: State;
  items: SavedItem[];
  companies: State['companies'];
  onChanged: () => void;
  notify: (m: string) => void;
  refresh: () => Promise<void>;
}) {
  const [target, setTarget] = useState(companyId || '');
  const [counts, setCounts] = useState<Counts | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [write, setWrite] = useState<{
    destination: string;
    machine: string | null;
    files: { name: string; kind: string; period: string }[];
    left_out: { name: string; period: string }[];
  } | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [jobId, setJobId] = useState('');
  const job = state.jobs.find((j) => j.id === jobId);
  const result = job?.result as
    | {
        escritos?: number;
        duplicados?: number;
        errores?: number;
        cancelado?: boolean;
        error?: string;
        progreso?: { total: number; hechas: number };
      }
    | undefined;
  useEffect(() => {
    setCounts(null);
    setWrite(null);
    setConfirmed(false);
    setError('');
  }, [runId]);
  useEffect(() => {
    if (!job || !['queued', 'running'].includes(job.status)) return;
    const timer = setInterval(() => void refresh().catch(() => undefined), 2500);
    return () => clearInterval(timer);
  }, [job, refresh]);
  const accepted = items.filter((i) => i.state === 'saved' || i.state === 'ya_registrado').length;
  async function preview() {
    setBusy(true);
    setError('');
    try {
      const r = await api<{ counts: Counts }>(
        '/organizador/runs/' + runId + '/save-preview?company_id=' + encodeURIComponent(target),
      );
      setCounts(r.counts);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    setError('');
    try {
      await api('/organizador/runs/' + runId + '/save', 'POST', { company_id: target });
      notify('Guardado en el expediente. Los archivos bloqueados o en revisión esperan en Por revisar › CFDI.');
      setCounts(null);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function loadWrite() {
    setError('');
    try {
      setWrite(await api('/organizador/runs/' + runId + '/write-folder-preview'));
      setConfirmed(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function startWrite() {
    setBusy(true);
    setError('');
    try {
      const r = await api<{ id: string }>('/organizador/runs/' + runId + '/write-folder', 'POST', { confirm: true });
      setJobId(r.id);
      setWrite(null);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    try {
      await api('/jobs/' + jobId + '/cancel', 'POST');
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className={stitchCard + ' padded'} aria-labelledby="cfdi-expediente-title">
      <h2 id="cfdi-expediente-title">Expediente</h2>
      <p className="muted">
        Guarda en el Centro Documental los XML, PDF y reportes Excel (.xlsx) de este análisis; los reportes se guardan
        tal cual, sin leer su contenido. Los archivos con incoherencia (RFC o fecha), conflicto de contenido o que ya
        existan ligados a otra empresa se envían a Por revisar › CFDI; nada se sobrescribe ni se fusiona.
      </p>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {!companyId && (
        <select aria-label="Empresa del expediente" value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">Elegir empresa…</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} · {c.rfc}
            </option>
          ))}
        </select>
      )}
      <div className="actions">
        <button className={stitchButton} disabled={busy || !target} onClick={() => void preview()}>
          Revisar contra el expediente
        </button>
      </div>
      {counts && (
        <div role="status">
          <p>
            <Badge tone="green">{counts.nuevo} nuevos</Badge> <Badge>{counts.ya_registrado} ya registrados</Badge>{' '}
            <Badge tone="amber">{counts.revision} en revisión</Badge>{' '}
            <Badge tone="red">{counts.bloqueado} bloqueados</Badge>
          </p>
          <button className={stitchPrimary} disabled={busy} onClick={() => void save()}>
            Guardar en expediente
          </button>
        </div>
      )}
      {!!items.length && (
        <details>
          <summary>
            Estado de guardado (
            {Object.entries(
              items.reduce<Record<string, number>>((acc, i) => ({ ...acc, [i.state]: (acc[i.state] || 0) + 1 }), {}),
            )
              .map(([k, n]) => (SAVE_STATE[k] || k) + ' ' + n)
              .join(' · ')}
            )
          </summary>
          <ul>
            {items.map((i) => (
              <li key={i.id}>
                {i.name} · {SAVE_STATE[i.state] || i.state}
                {i.reasons.length > 0 && ' · ' + i.reasons.map((r) => INCOHERENCE[r] || r).join(', ')}
              </li>
            ))}
          </ul>
        </details>
      )}
      <h3>Carpeta de la empresa</h3>
      <p className="muted">
        Con tu agente local puedes copiar los archivos aceptados a la carpeta física de la empresa (
        <code>MM.- MES / EMITIDOS o RECIBIDOS</code>). Sólo se copia: un nombre existente se reporta como Duplicado y
        nunca se sobrescribe; cada archivo se verifica con SHA-256.
      </p>
      <div className="actions">
        <button className={stitchButton} disabled={busy || !accepted} onClick={() => void loadWrite()}>
          Escribir en carpeta de la empresa
        </button>
      </div>
      {write && (
        <div className="info-box" role="group" aria-label="Confirmar escritura en la carpeta de la empresa">
          <p>
            Destino: <strong className="path-text">{write.destination}</strong>
            {write.machine && ' · en ' + write.machine}
          </p>
          <p>{write.files.length} archivos se copiarán:</p>
          <ul>
            {write.files.slice(0, 15).map((f) => (
              <li key={f.name + f.period}>
                {f.name} · {f.kind} · {f.period}
              </li>
            ))}
            {write.files.length > 15 && <li>y {write.files.length - 15} más</li>}
          </ul>
          {write.left_out.length > 0 && (
            <p className="muted">{write.left_out.length} archivos de otro ejercicio no se incluyen.</p>
          )}
          <label>
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /> Confirmo que
            se escriban estos archivos en esa carpeta.
          </label>
          <div className="actions">
            <button className={stitchPrimary} disabled={!confirmed || busy} onClick={() => void startWrite()}>
              Escribir ahora
            </button>
            <button className={stitchButton} onClick={() => setWrite(null)}>
              Cancelar
            </button>
          </div>
        </div>
      )}
      {job && (
        <p role="status">
          {job.status === 'queued' && 'Esperando a tu agente…'}
          {job.status === 'running' &&
            'Escribiendo' + (result?.progreso ? `: ${result.progreso.hechas} de ${result.progreso.total}` : '…') + ' '}
          {job.status === 'running' && (
            <button className={stitchButton} onClick={() => void cancel()}>
              Cancelar
            </button>
          )}
          {job.status === 'completed' &&
            `Terminado${result?.cancelado ? ' (cancelado)' : ''}: ${result?.escritos ?? 0} escritos · ${result?.duplicados ?? 0} duplicados · ${result?.errores ?? 0} errores · ${dateLabel(job.created_at)}`}
          {job.status === 'failed' && 'No se pudo escribir: ' + (result?.error || 'sin detalle')}
        </p>
      )}
    </section>
  );
}
