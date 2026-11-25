import { stitchButton, stitchPrimary, stitchCard } from '../components/stitch';
import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  Clock3,
  Download,
  Eye,
  FileText,
  FolderOpen,
  History,
  MinusCircle,
  RefreshCw,
  Upload,
} from 'lucide-react';
import { api, getToken, dateLabel } from '../api';
import { Badge, Empty, Field, Heading, Kpi } from '../components/ui';
import type { State } from '../types';
// Counters reported by the Recopila engine adapter; any other keys are informative only.
type RunSummary = {
  policy_pages?: number;
  policy_pdf_files?: number;
  policies_with_document?: number;
  policies_without_document?: number;
  leftover_cfdi_pdfs?: number;
  cfdi_xml_parsed?: number;
  months_desc?: string[];
  [key: string]: unknown;
};
type Run = {
  id: string;
  company_id: string | null;
  name: string;
  status: string;
  message: string;
  summary: RunSummary;
  warnings: string[];
  by_month: boolean;
  created_at: string;
};
type Policy = {
  source: string;
  page: number;
  index?: number;
  support?: string;
  missing?: string[];
  type: string;
  date: string;
  month: string;
  description: string;
  uuids: string[];
  matches: string[];
  status: string;
  section: string;
};
type Proposal = { id: string; policy_index: number; kind: string; uuid: string; pdf: string };
type ReviewItem = { kind: string; uuid: string; policy_index: number | null };
type Adjustment = {
  id: string;
  policy_idx: number;
  action: string;
  target: string;
  actor_id: string;
  created_at: string;
  revoked_at: string | null;
};
type Enrichment = {
  proposals: Proposal[];
  review: ReviewItem[];
  leftover_items: { pdf: string; uuid: string; category: string }[];
  leftover_categories: Record<string, number>;
  unsupported: { pages: number; contalink_hint: boolean };
};
type Detail = {
  run: Run;
  policies: Policy[];
  leftovers: string[];
  outputs: { name: string; size: number }[];
  enrichment?: Enrichment | null;
  adjustments?: Adjustment[];
};
const support: Record<string, string> = {
  Completa: 'green',
  Parcial: 'amber',
  'XML sin PDF': 'amber',
  'Sin soporte': 'red',
};
const proposalKinds: Record<string, string> = {
  complemento_directo: 'UUID del complemento en la póliza de pago/cobro',
  diario: 'CFDI citado en una póliza de diario',
};
const categories: Record<string, string> = {
  ingresos: 'Ingresos',
  egresos: 'Egresos',
  nomina: 'Nómina',
  complementos: 'Complementos',
  otro_periodo: 'Otro periodo',
  otro: 'Otros',
};
const reviewKinds: Record<string, string> = {
  rfc_ajeno: 'RFC ajeno a la empresa',
  pareja_no_verificada: 'Pareja XML–PDF no verificada',
};
const labels: Record<string, string> = {
  analyzing: 'Analizando',
  analyzed: 'Listo para revisar',
  generating: 'Generando',
  generated: 'Terminado',
  error: 'Revisar error',
};
/** Rediseño v2: state of a policy and of an analysis with icon and text (never color alone). */
function PolicyState({ status }: { status: string }) {
  const done = status === 'RELACIONADO';
  const diary = status === 'POLIZA_SOLA_DIARIO';
  const Icon = done ? CheckCircle2 : diary ? MinusCircle : AlertTriangle;
  return (
    <span className={'v2-state ' + (done ? 'is-done' : diary ? 'is-muted' : 'is-warn')}>
      <Icon size={13} aria-hidden /> {states[status] || status}
    </span>
  );
}
function RunState({ status }: { status: string }) {
  const Icon = status === 'generated' ? CheckCircle2 : status === 'error' ? AlertTriangle : Clock3;
  const tone = status === 'generated' ? 'is-done' : status === 'error' ? 'is-error' : 'is-ready';
  return (
    <span className={'v2-state ' + tone}>
      <Icon size={13} aria-hidden /> {labels[status] || status}
    </span>
  );
}
const states: Record<string, string> = {
  RELACIONADO: 'Relacionado',
  POLIZA_SOLA_DIARIO: 'Póliza de diario',
  POLIZA_SOLA_SIN_DOCUMENTO: 'Sin documento relacionado',
};
async function blob(path: string, signal?: AbortSignal) {
  const response = await fetch('/api/recopila' + path, { headers: { Authorization: 'Bearer ' + getToken() }, signal });
  if (!response.ok) {
    const e = await response.json().catch(() => ({}));
    throw new Error(typeof e.detail === 'string' ? e.detail : 'No se pudo obtener el archivo.');
  }
  return response.blob();
}
function saveFile(data: Blob, name: string) {
  const url = URL.createObjectURL(data);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}
export default function Recopila({
  state,
  notify,
  refresh,
}: {
  state: State;
  notify: (m: string) => void;
  refresh: () => Promise<void>;
}) {
  const [params] = useSearchParams();
  const [company, setCompany] = useState(params.get('empresa') || '');
  const [files, setFiles] = useState<File[]>([]);
  const [ignored, setIgnored] = useState(0);
  const [runs, setRuns] = useState<Run[]>([]);
  const [id, setId] = useState('');
  const [detail, setDetail] = useState<Detail | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [monthly, setMonthly] = useState(false);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('');
  const [month, setMonth] = useState('');
  const [page, setPage] = useState(0);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [preview, setPreview] = useState<{ name: string; kind: 'input' | 'output'; page?: number } | null>(null);
  const [pdf, setPdf] = useState('');
  const [pdfError, setPdfError] = useState('');
  const [supportFilter, setSupportFilter] = useState('');
  const [period, setPeriod] = useState('');
  const [savingCompany, setSavingCompany] = useState('');
  const [saved, setSaved] = useState<{ name: string; status: string }[]>([]);
  const zipRef = useRef<HTMLInputElement>(null);
  const docsRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const previewRef = useRef('');
  const working = uploading || ['analyzing', 'generating'].includes(detail?.run.status || '');
  useEffect(() => {
    const open = params.get('analisis');
    if (open) setId(open);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    folderRef.current?.setAttribute('webkitdirectory', '');
    api<Run[]>('/recopila/runs')
      .then(setRuns)
      .catch((e) => setError(e.message));
    return () => URL.revokeObjectURL(previewRef.current);
  }, []);
  useEffect(() => {
    if (!id) {
      setDetail(null);
      return;
    }
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const d = await api<Detail>('/recopila/runs/' + id);
        if (!active) return;
        setDetail(d);
        if (['analyzing', 'generating'].includes(d.run.status)) timer = setTimeout(load, 1200);
        else {
          setMonthly(d.run.by_month);
          api<Run[]>('/recopila/runs')
            .then((v) => {
              if (active) setRuns(v);
            })
            .catch(() => {});
          refresh().catch(() => {});
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    };
    load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [id, detail?.run.status, refresh]);
  useEffect(() => {
    setPage(0);
  }, [query, filter, month, id]);
  useEffect(() => {
    setPdf('');
    setPdfError('');
    if (!preview) return;
    const controller = new AbortController();
    blob('/runs/' + id + '/file?' + new URLSearchParams({ name: preview.name, kind: preview.kind }), controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        URL.revokeObjectURL(previewRef.current);
        previewRef.current = URL.createObjectURL(data);
        setPdf(previewRef.current);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setPdfError(e.message);
      });
    return () => controller.abort();
  }, [id, preview]);
  function choose(list: FileList | null) {
    if (!list) return;
    const incoming = Array.from(list);
    const selected = incoming.filter((f) => /\.(pdf|xml|zip)$/i.test(f.name));
    setIgnored(incoming.length - selected.length);
    setFiles(selected);
    setError('');
  }
  async function analyze() {
    setError('');
    if (!files.length) {
      setError('Selecciona un ZIP, una carpeta o documentos PDF/XML.');
      return;
    }
    if (files.length > 1000) {
      setError('Selecciona hasta 1,000 documentos o un ZIP con hasta 5,000 documentos.');
      return;
    }
    if (files.some((f) => /\.zip$/i.test(f.name)) && files.length !== 1) {
      setError('Carga un único ZIP o selecciona documentos PDF/XML.');
      return;
    }
    if (files.reduce((n, f) => n + f.size, 0) > 100 * 1024 * 1024) {
      setError('La carga admite hasta 100 MB por análisis.');
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      form.append('company_id', company);
      for (const file of files) form.append('files', file, file.webkitRelativePath || file.name);
      const r = await api<Run>('/recopila/runs', 'POST', form);
      setDetail({ run: r, policies: [], leftovers: [], outputs: [] });
      setId(r.id);
      setPreview(null);
      setPolicy(null);
      setQuery('');
      setFilter('');
      setMonth('');
      notify('Documentos cargados. Comenzó el análisis.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }
  async function fromCompany() {
    setError('');
    setUploading(true);
    try {
      const r = await api<Run>('/recopila/runs/from-company', 'POST', { company_id: company, period });
      setDetail({ run: r, policies: [], leftovers: [], outputs: [] });
      setId(r.id);
      setPreview(null);
      setPolicy(null);
      notify('Documentos de la empresa cargados. Comenzó el análisis.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }
  async function adjust(action: 'attach' | 'remove', policyIndex: number, target: string) {
    setError('');
    try {
      const list = await api<Adjustment[]>('/recopila/runs/' + id + '/adjustments', 'POST', {
        policy_index: policyIndex,
        action,
        target,
      });
      setDetail((d) => (d ? { ...d, adjustments: list } : d));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function undo(adjustmentId: string) {
    try {
      const list = await api<Adjustment[]>('/recopila/runs/' + id + '/adjustments/' + adjustmentId, 'DELETE');
      setDetail((d) => (d ? { ...d, adjustments: list } : d));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function saveToExpediente() {
    setError('');
    const target = detail?.run.company_id || savingCompany;
    if (!target) {
      setError('Elige la empresa del expediente donde se guardará.');
      return;
    }
    if (!window.confirm('¿Guardar RECOPILADOR en el Centro Documental de esa empresa? No se sobrescribe nada.')) return;
    try {
      const r = await api<{ files: { name: string; status: string }[] }>('/recopila/runs/' + id + '/save', 'POST', {
        company_id: target,
      });
      setSaved(r.files);
      notify('Guardado en el expediente.');
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function generate() {
    setError('');
    try {
      await api('/recopila/runs/' + id + '/generate', 'POST', { by_month: monthly });
      setDetail((d) => (d ? { ...d, run: { ...d.run, status: 'generating', message: 'Generando documentos…' } } : d));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function download(name: string) {
    try {
      saveFile(
        await blob('/runs/' + id + '/file?' + new URLSearchParams({ name, kind: 'output' })),
        name.split('/').pop() || name,
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function downloadZip() {
    try {
      saveFile(await blob('/runs/' + id + '/zip'), 'RECOPILADOR_RESULTADOS.zip');
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function openRun(next: string) {
    setId(next);
    setPreview(null);
    setPolicy(null);
    setError('');
    setDetail(null);
  }
  const summary: RunSummary = detail?.run.summary || {};
  const policies = (detail?.policies || []).filter(
    (p) =>
      (!filter || p.status === filter) &&
      (!supportFilter || p.support === supportFilter) &&
      (!month || p.month === month) &&
      `${p.source} ${p.type} ${p.description} ${p.date} ${p.uuids.join(' ')}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const visible = policies.slice(page * 50, page * 50 + 50);
  return (
    <div className="recopila-module stitch-live-module">
      <Heading
        eyebrow="ORGANIZACIÓN DOCUMENTAL"
        title="Recopila"
        description="Relaciona pólizas con sus comprobantes y prepara los PDF del recopilador."
      />
      <ol className="recopila-steps v2-steps" aria-label="Pasos de Recopila">
        {(
          [
            ['1 · Cargar y analizar', !!detail, !detail],
            ['2 · Revisar coincidencias', detail?.run.status === 'generated', !!detail?.policies.length],
            ['3 · Generar archivos', detail?.run.status === 'generated', false],
          ] as const
        ).map(([label, done, current]) => (
          <li key={label} className={done ? 'is-done' : current ? 'is-current' : ''}>
            {done && <CheckCircle2 size={15} aria-hidden />}
            {label}
            {done && <span className="sr-only"> (completado)</span>}
          </li>
        ))}
      </ol>
      {error && (
        <div className="error-banner" role="alert">
          {error}
          <button onClick={() => setError('')}>Cerrar</button>
        </div>
      )}
      <div className="v2-recopila-top">
        <section className={stitchCard + ' padded v2-recopila-params'}>
          <h2>Documentos a relacionar</h2>
          <p className="muted">Pólizas del «Impreso de pólizas» de CONTPAQi con los PDF y XML de sus CFDI.</p>
          <div>
            <Field label="Empresa (opcional)">
              <select value={company} disabled={working} onChange={(e) => setCompany(e.target.value)}>
                <option value="">Sin vincular a una empresa</option>
                {state.companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} · {c.rfc}
                  </option>
                ))}
              </select>
            </Field>
            <div className="actions">
              <button className={stitchButton} disabled={working} onClick={() => zipRef.current?.click()}>
                <Archive size={16} />
                Cargar ZIP
              </button>
              <button className={stitchButton} disabled={working} onClick={() => folderRef.current?.click()}>
                <FolderOpen size={16} />
                Elegir carpeta
              </button>
              <button className={stitchButton} disabled={working} onClick={() => docsRef.current?.click()}>
                <Upload size={16} />
                Agregar documentos
              </button>
            </div>
            <input
              ref={zipRef}
              type="file"
              accept=".zip"
              hidden
              onChange={(e) => {
                choose(e.target.files);
                e.target.value = '';
              }}
            />
            <input
              ref={docsRef}
              type="file"
              multiple
              accept=".pdf,.xml"
              hidden
              onChange={(e) => {
                choose(e.target.files);
                e.target.value = '';
              }}
            />
            <input
              ref={folderRef}
              type="file"
              multiple
              hidden
              onChange={(e) => {
                choose(e.target.files);
                e.target.value = '';
              }}
            />
            <div className="actions">
              <input
                type="month"
                aria-label="Periodo de los documentos de la empresa"
                value={period}
                disabled={working}
                onChange={(e) => setPeriod(e.target.value)}
              />
              <button
                className={stitchButton}
                disabled={working || !company || !/^20\d\d-(0[1-9]|1[0-2])$/.test(period)}
                onClick={fromCompany}
              >
                Usar documentos de la empresa
              </button>
            </div>
            <p className="muted recopila-file-description">
              {files.length
                ? `${files.length} archivo(s) · ${(files.reduce((n, f) => n + f.size, 0) / 1024 / 1024).toFixed(1)} MB`
                : 'Selecciona las pólizas, PDF de CFDI y sus XML.'}
              {ignored > 0 && ` Se omitieron ${ignored} archivos de otros formatos.`}
            </p>
            <small className="muted">
              Hasta 100 MB de carga. Se trabaja con copias; los originales de tu equipo se conservan.
            </small>
          </div>
          <button className={stitchPrimary + ' v2-wide'} disabled={working || !files.length} onClick={analyze}>
            {uploading ? 'Cargando…' : working ? 'Proceso en curso…' : 'Analizar documentos'}
          </button>
        </section>
        <section className={stitchCard + ' padded v2-recopila-history'} aria-labelledby="recopila-history-title">
          <h2 id="recopila-history-title">
            <History size={19} aria-hidden /> Historial de análisis
          </h2>
          <p className="muted">Abre un análisis anterior para revisarlo, generar sus archivos o guardarlo.</p>
          {runs.length ? (
            <ul>
              {runs.map((r) => (
                <li key={r.id}>
                  <button type="button" aria-pressed={r.id === id} disabled={working} onClick={() => openRun(r.id)}>
                    <span>
                      <strong>{r.name}</strong>
                      <small>{dateLabel(r.created_at)}</small>
                    </span>
                    <RunState status={r.status} />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="v2-empty muted">Todavía no hay análisis.</p>
          )}
        </section>
      </div>
      {detail && (
        <>
          <div className="recopila-status" role="status">
            {working && <RefreshCw size={16} className="recopila-spinner" />}
            <Badge tone={detail.run.status === 'error' ? 'red' : detail.run.status === 'generated' ? 'green' : 'blue'}>
              {labels[detail.run.status]}
            </Badge>
            <span>{detail.run.message}</span>
          </div>
          {detail.run.warnings.map((w, i) => (
            <p className="recopila-warning" key={i}>
              {w}
            </p>
          ))}
          {!!detail.enrichment?.unsupported.pages && (
            <p className="recopila-warning" role="status">
              {detail.enrichment.unsupported.pages === 1
                ? '1 página parece una póliza'
                : detail.enrichment.unsupported.pages + ' páginas parecen pólizas'}{' '}
              en un formato no compatible
              {detail.enrichment.unsupported.contalink_hint ? ' (Contalink)' : ''}. Aún no se leen: Recopila sólo
              interpreta el «Impreso de pólizas» de CONTPAQi.
            </p>
          )}
          {!!detail.enrichment?.review.length && (
            <details className={stitchCard + ' padded'}>
              <summary>Por revisar ({detail.enrichment.review.length})</summary>
              <ul>
                {detail.enrichment.review.map((r, i) => (
                  <li key={r.kind + r.uuid + i}>
                    {reviewKinds[r.kind] || r.kind} · <span className="recopila-uuids">{r.uuid}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
          <div className="kpi-grid four v2-kpis">
            <Kpi
              label="Pólizas detectadas"
              value={summary.policy_pages || 0}
              detail={`${summary.policy_pdf_files || 0} archivos de pólizas`}
            />
            <Kpi
              label="Con documento"
              value={summary.policies_with_document || 0}
              detail="Coincidencias por UUID"
              tone="green"
            />
            <Kpi
              label="Pólizas sin documento"
              value={summary.policies_without_document || 0}
              detail="Se conservan en el recopilador"
              tone="amber"
            />
            <Kpi
              label="Sobrantes"
              value={summary.leftover_cfdi_pdfs || 0}
              detail={`${summary.cfdi_xml_parsed || 0} CFDI interpretados`}
            />
          </div>
          <div className="recopila-workspace">
            <div className="recopila-review">
              <section className={stitchCard + ' padded'}>
                <div className="receipt-section-title">
                  <h2>Revisión de pólizas</h2>
                  <Badge>{policies.length}</Badge>
                </div>
                <div className="recopila-filters">
                  <Field label="Buscar descripción, archivo o UUID">
                    <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar documentos…" />
                  </Field>
                  <Field label="Estado">
                    <select value={filter} onChange={(e) => setFilter(e.target.value)}>
                      <option value="">Todos los estados</option>
                      {Object.entries(states).map(([k, v]) => (
                        <option key={k} value={k}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Soporte">
                    <select value={supportFilter} onChange={(e) => setSupportFilter(e.target.value)}>
                      <option value="">Todos</option>
                      {Object.keys(support).map((k) => (
                        <option key={k}>{k}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Mes">
                    <select value={month} onChange={(e) => setMonth(e.target.value)}>
                      <option value="">Todos los meses</option>
                      {(summary.months_desc || []).map((m: string) => (
                        <option key={m}>{m}</option>
                      ))}
                    </select>
                  </Field>
                </div>
                <div className="receipt-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Póliza</th>
                        <th>Tipo / periodo</th>
                        <th>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visible.map((p) => (
                        <tr
                          key={p.source + ':' + p.page}
                          className={policy?.source === p.source && policy?.page === p.page ? 'receipt-selected' : ''}
                        >
                          <td>
                            <button
                              className="receipt-text-button"
                              onClick={() => {
                                setPolicy(p);
                                setPreview({ name: p.source, kind: 'input', page: p.page });
                              }}
                            >
                              <strong>{p.description || p.source.split('/').pop()}</strong>
                              <small>
                                {p.source} · página {p.page}
                              </small>
                            </button>
                          </td>
                          <td>
                            {p.type}
                            <small>
                              {p.date || 'Fecha no detectada'} · {p.month || 'Sin mes'}
                            </small>
                          </td>
                          <td>
                            <PolicyState status={p.status} />
                            {p.support && (
                              <small>
                                <Badge tone={support[p.support] || 'neutral'}>{p.support}</Badge>
                                {!!p.missing?.length && ' · faltan ' + p.missing.length + ' UUID'}
                              </small>
                            )}
                            <small>{p.matches.length} documento(s)</small>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!policies.length && (
                    <Empty title={working ? 'Analizando documentos…' : 'Sin pólizas para mostrar'}>
                      El motor reconoce pólizas con texto extraíble y los formatos de la aplicación de escritorio.
                    </Empty>
                  )}
                </div>
                <div className="recopila-pagination">
                  <button className={stitchButton} disabled={!page} onClick={() => setPage((v) => v - 1)}>
                    Anterior
                  </button>
                  <span>
                    Página {page + 1} de {Math.max(1, Math.ceil(policies.length / 50))}
                  </span>
                  <button
                    className={stitchButton}
                    disabled={(page + 1) * 50 >= policies.length}
                    onClick={() => setPage((v) => v + 1)}
                  >
                    Siguiente
                  </button>
                </div>
              </section>
              {policy && (
                <section className={stitchCard + ' padded'}>
                  <h2>Detalle de la póliza</h2>
                  <p className="muted">
                    {policy.type} · {policy.date} · {policy.section}
                  </p>
                  <p className="recopila-uuids">
                    {policy.uuids.length ? policy.uuids.join(' · ') : 'Sin UUID asociado'}
                  </p>
                  {!!policy.missing?.length && (
                    <p className="muted">UUID sin documento completo: {policy.missing.join(' · ')}</p>
                  )}
                  {policy.index !== undefined &&
                    detail.enrichment?.proposals
                      .filter((x) => x.policy_index === policy.index)
                      .map((x) => (
                        <p key={x.id}>
                          <strong>Propuesta:</strong> {proposalKinds[x.kind] || x.kind} · {x.uuid}{' '}
                          <button
                            className={stitchButton}
                            disabled={working || detail.run.status === 'generating'}
                            onClick={() => adjust('attach', policy.index!, x.pdf)}
                          >
                            Aceptar propuesta
                          </button>
                        </p>
                      ))}
                  {policy.index !== undefined && !!detail.enrichment?.leftover_items.length && (
                    <details>
                      <summary>Asociar un sobrante a esta póliza</summary>
                      <ul>
                        {detail.enrichment.leftover_items.map((x) => (
                          <li key={x.pdf}>
                            {categories[x.category] || x.category} · {x.uuid || x.pdf}{' '}
                            <button className={stitchButton} onClick={() => adjust('attach', policy.index!, x.pdf)}>
                              Asociar
                            </button>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                  <div className="actions">
                    <button
                      className={stitchButton}
                      onClick={() => setPreview({ name: policy.source, kind: 'input', page: policy.page })}
                    >
                      <Eye size={15} />
                      Ver póliza
                    </button>
                    {policy.matches.map((name, i) => (
                      <button key={name} className={stitchButton} onClick={() => setPreview({ name, kind: 'input' })}>
                        Ver documento {i + 1}
                      </button>
                    ))}
                  </div>
                </section>
              )}
              {!!detail.leftovers.length && (
                <details className={stitchCard + ' padded recopila-leftovers'}>
                  <summary>
                    Documentos sobrantes ({detail.leftovers.length})
                    {detail.enrichment &&
                      ' · ' +
                        Object.entries(detail.enrichment.leftover_categories)
                          .map(([k, n]) => (categories[k] || k) + ' ' + n)
                          .join(' · ')}
                  </summary>
                  <ul>
                    {detail.leftovers.map((name) => (
                      <li key={name}>
                        <button className="receipt-text-button" onClick={() => setPreview({ name, kind: 'input' })}>
                          <Eye size={14} />
                          {name}
                        </button>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {!!detail.adjustments?.length && (
                <section className={stitchCard + ' padded'}>
                  <h2>Ajustes manuales</h2>
                  <ul>
                    {detail.adjustments.map((a) => (
                      <li key={a.id}>
                        {a.action === 'attach' ? 'Asociar' : 'Quitar'} {a.target.split('/').pop()} · póliza{' '}
                        {a.policy_idx + 1} · {dateLabel(a.created_at)}
                        {a.revoked_at ? (
                          ' · revertido'
                        ) : (
                          <button className={stitchButton} onClick={() => undo(a.id)}>
                            Revertir
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              <section className={stitchCard + ' padded'}>
                <h2>Archivos de salida</h2>
                <label className="receipt-multi-toggle recopila-month-toggle">
                  <input
                    type="checkbox"
                    checked={monthly}
                    disabled={working}
                    onChange={(e) => setMonthly(e.target.checked)}
                  />
                  Generar también archivos por mes
                </label>
                <p className="muted">
                  Se generan el recopilador completo, sobrantes, separadores de meses y reportes de revisión.
                </p>
                <div className="actions">
                  <button className={stitchPrimary} disabled={working || !detail.policies.length} onClick={generate}>
                    {detail.run.status === 'generating' ? 'Generando…' : 'Generar archivos'}
                  </button>
                  {detail.run.status === 'generated' && (
                    <button className={stitchButton} onClick={downloadZip}>
                      <Download size={16} />
                      Descargar todos (ZIP)
                    </button>
                  )}
                </div>
                {detail.run.status === 'generated' && (
                  <div className="actions">
                    {!detail.run.company_id && (
                      <select
                        aria-label="Empresa del expediente"
                        value={savingCompany}
                        onChange={(e) => setSavingCompany(e.target.value)}
                      >
                        <option value="">Elegir empresa…</option>
                        {state.companies.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name} · {c.rfc}
                          </option>
                        ))}
                      </select>
                    )}
                    <button className={stitchButton} onClick={saveToExpediente}>
                      Guardar en expediente
                    </button>
                  </div>
                )}
                {saved.map((f) => (
                  <small key={f.name} className="muted">
                    {f.name}:{' '}
                    {{
                      nuevo: 'documento nuevo',
                      version_nueva: 'versión nueva',
                      ya_registrado: 'ya estaba registrado',
                    }[f.status] || f.status}
                  </small>
                ))}
                {!!detail.outputs.length && (
                  <ul className="recopila-outputs">
                    {detail.outputs.map((f) => (
                      <li key={f.name}>
                        <span>
                          {f.name}
                          <small className="muted">{(f.size / 1024).toFixed(1)} KB</small>
                        </span>
                        <div className="actions">
                          {f.name.endsWith('.pdf') && (
                            <button
                              className="icon-button"
                              aria-label={'Ver ' + f.name}
                              onClick={() => setPreview({ name: f.name, kind: 'output' })}
                            >
                              <Eye size={16} />
                            </button>
                          )}
                          <button
                            className="icon-button"
                            aria-label={'Descargar ' + f.name}
                            onClick={() => download(f.name)}
                          >
                            <Download size={16} />
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
            <aside className={stitchCard + ' receipt-preview'}>
              <div className="receipt-preview-head">
                <div>
                  <h2>Vista previa</h2>
                  <small>{preview?.name.split('/').pop() || 'Selecciona una póliza o documento'}</small>
                </div>
              </div>
              <div className="receipt-paper">
                {pdf ? (
                  <iframe
                    title="PDF del recopilador"
                    key={pdf + preview?.page}
                    src={pdf + '#toolbar=1&navpanes=0&zoom=page-fit&page=' + (preview?.page || 1)}
                  />
                ) : (
                  <div className="empty">
                    <FileText size={32} />
                    <p>
                      {pdfError ||
                        (preview ? 'Cargando PDF…' : 'Selecciona una fila para revisar la póliza y sus comprobantes.')}
                    </p>
                  </div>
                )}
              </div>
            </aside>
          </div>
        </>
      )}
      {!detail && (
        <Empty title="Carga los documentos para comenzar">
          Puedes usar un ZIP, una carpeta o seleccionar varios PDF y XML.
        </Empty>
      )}
    </div>
  );
}
