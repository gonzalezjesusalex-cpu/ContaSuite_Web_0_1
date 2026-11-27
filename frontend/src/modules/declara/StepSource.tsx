import { useEffect, useRef, useState, type DragEvent } from 'react';
import { Link } from 'react-router-dom';
import { Archive, Download, ExternalLink, FolderOpen, HardDrive, RefreshCw, Upload } from 'lucide-react';
import { dateLabel } from '../../api';
import { Badge, Field } from '../../components/ui';
import { stitchButton, stitchCard, stitchPrimary } from '../../components/stitch';
import type { State } from '../../types';
import SatAccess from '../SatAccess';
import FolderSource from './FolderSource';
import MonthMatrix from './MonthMatrix';
import { RUN_LABELS, longDate, sanitizeShortName, type CompanyView, type Run } from './model';

const MAX_FILES = 1000;
const MAX_BYTES = 100 * 1024 * 1024;

export type Mode = 'subir' | 'carpeta';

function PreviousRuns({ runs, onOpen, busy }: { runs: Run[]; onOpen: (id: string) => void; busy: boolean }) {
  const years = Array.from(new Set(runs.map((r) => r.year || 0))).sort((a, b) => b - a);
  return (
    <section className={stitchCard + ' padded declara-side-card'}>
      <h2>Análisis anteriores</h2>
      {!runs.length && <p className="muted">Esta empresa aún no tiene análisis.</p>}
      {years.map((y) => (
        <div key={y} className="declara-runs-year">
          <h3>{y ? `Ejercicio ${y}` : 'Sin ejercicio'}</h3>
          <ul>
            {runs
              .filter((r) => (r.year || 0) === y)
              .slice(0, 6)
              .map((r) => {
                const pending = r.summary?.rename || 0;
                const resumable = r.status === 'analyzed';
                return (
                  <li key={r.id}>
                    <div>
                      <strong>{r.summary?.total ?? '—'} PDF</strong>
                      <small>
                        {dateLabel(r.created_at)} · {RUN_LABELS[r.status] || r.status}
                        {resumable && pending ? ` · ${pending} pendientes` : ''}
                      </small>
                    </div>
                    <button type="button" className={stitchButton} disabled={busy} onClick={() => onOpen(r.id)}>
                      {resumable ? 'Reanudar' : 'Abrir'}
                    </button>
                  </li>
                );
              })}
          </ul>
        </div>
      ))}
    </section>
  );
}

/** Tarjeta «Sesión SAT» del modo carpeta: el agente descarga directo a la carpeta vinculada. */
function FolderSat({
  agentOnline,
  machine,
  portal,
  lastRun,
  onSat,
}: {
  agentOnline: boolean;
  machine: string;
  portal: boolean;
  lastRun: Run | undefined;
  onSat: (runId: string) => void;
}) {
  return (
    <div className="declara-folder-sat">
      <ul className="declara-sat-checks">
        <li>Agente: {agentOnline ? `conectado${machine ? ' · ' + machine : ''}` : 'sin conexión'}</li>
        <li>Portal SAT en el agente: {portal ? 'habilitado' : 'no habilitado en este equipo'}</li>
        <li>e.firma: la toma del gestor de contraseñas al iniciar (con la bóveda desbloqueada)</li>
        <li>Ruta: Portal → Personas morales → «Pagos provisionales del ISR»</li>
      </ul>
      {!lastRun && <p className="muted">Analiza primero la carpeta: la sesión descarga sólo lo que falta en ella.</p>}
      <div className="actions">
        <button
          type="button"
          className={stitchButton}
          disabled={!portal || !agentOnline || !lastRun}
          onClick={() => lastRun && onSat(lastRun.id)}
        >
          <Download size={16} />
          Descargar faltantes
        </button>
        <a className={stitchButton} href="https://www.sat.gob.mx/" target="_blank" rel="noreferrer noopener">
          <ExternalLink size={16} />
          Abrir portal SAT
        </a>
      </div>
    </div>
  );
}

/** Paso 1 · Empresa y PDF. */
export default function StepSource({
  state,
  company,
  onCompany,
  year,
  onYear,
  shortName,
  onShortName,
  view,
  mode,
  onMode,
  runs,
  busy,
  onAnalyze,
  onOpenRun,
  notify,
  refresh,
  folder,
}: {
  state: State;
  company: string;
  onCompany: (id: string) => void;
  year: number;
  onYear: (y: number) => void;
  shortName: string;
  onShortName: (v: string) => void;
  view: CompanyView | null;
  mode: Mode;
  onMode: (m: Mode) => void;
  runs: Run[];
  busy: boolean;
  onAnalyze: (files: File[]) => Promise<void>;
  onOpenRun: (id: string) => void;
  notify: (m: string) => void;
  refresh: () => Promise<void>;
  folder: {
    backup: boolean;
    poll: boolean;
    onBackup: (v: boolean) => void;
    onPoll: (v: boolean) => void;
    onSat: (runId: string) => void;
  };
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [problem, setProblem] = useState('');
  const [dragging, setDragging] = useState(false);
  const zipRef = useRef<HTMLInputElement>(null);
  const docsRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const thisYear = new Date().getFullYear();
  const clean = sanitizeShortName(shortName);
  const agent = state.agents.find((a) => a.id === state.agent_link?.agent_id);
  const folderReady = !!agent?.capabilities.includes('declara_carpeta');
  const ready = !!company && !!clean;
  useEffect(() => {
    folderRef.current?.setAttribute('webkitdirectory', '');
  }, []);

  function check(list: File[]) {
    const pdf = list.filter((f) => /\.(pdf|zip)$/i.test(f.name));
    if (!pdf.length) return 'Selecciona PDF, una carpeta de PDF o un único ZIP.';
    if (pdf.some((f) => /\.zip$/i.test(f.name)) && pdf.length !== 1) return 'Carga un único ZIP o selecciona PDF.';
    if (pdf.length > MAX_FILES || pdf.reduce((n, f) => n + f.size, 0) > MAX_BYTES)
      return 'Máximo 1,000 PDF y 100 MB por carga, o un ZIP con hasta 5,000 PDF.';
    return '';
  }
  // El análisis empieza al soltar (o al elegir) si la empresa y el nombre corto están listos.
  async function take(list: FileList | File[] | null) {
    const all = Array.from(list || []);
    if (!all.length) return;
    const message = check(all);
    setProblem(message);
    if (message) return;
    const chosen = all.filter((f) => /\.(pdf|zip)$/i.test(f.name));
    setFiles(chosen);
    if (ready) {
      await onAnalyze(chosen);
      setFiles([]);
    }
  }
  function drop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (!busy) void take(e.dataTransfer.files);
  }
  const example = `3.2.- ACUSE ISR E IVA MARZO ${clean || 'NOMBRE'}.pdf`;
  return (
    <div className="declara-step-grid">
      <div className="declara-step-main">
        <section className={stitchCard + ' padded'}>
          <h2 className="declara-card-title">Modo de trabajo</h2>
          <div className="declara-modes" role="radiogroup" aria-label="Modo de trabajo">
            <button
              type="button"
              role="radio"
              aria-checked={mode === 'carpeta'}
              disabled={!folderReady}
              className={'declara-mode' + (mode === 'carpeta' ? ' active' : '')}
              onClick={() => onMode('carpeta')}
            >
              <HardDrive size={20} />
              <strong>Carpeta del equipo o red</strong>
              <small>
                {folderReady
                  ? 'Analiza la carpeta, descarga ahí los faltantes del SAT y renombra en la misma carpeta.'
                  : 'El agente de este equipo todavía no admite el modo carpeta.'}
              </small>
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={mode === 'subir'}
              className={'declara-mode' + (mode === 'subir' ? ' active' : '')}
              onClick={() => onMode('subir')}
            >
              <Upload size={20} />
              <strong>Subir PDF o ZIP</strong>
              <small>Trabaja con copias; los originales no se tocan.</small>
            </button>
          </div>
        </section>

        <section className={stitchCard + ' padded'}>
          <fieldset disabled={busy} className="declara-fields">
            <Field label="Empresa">
              <select value={company} onChange={(e) => onCompany(e.target.value)}>
                <option value="">Selecciona una empresa</option>
                {state.companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} · {c.rfc}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Ejercicio">
              <select value={year} onChange={(e) => onYear(Number(e.target.value))}>
                {[1, 0, -1, -2, -3, -4, -5].map((n) => (
                  <option key={n} value={thisYear + n}>
                    {thisYear + n}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Nombre corto">
              <input
                maxLength={80}
                value={shortName}
                onChange={(e) => onShortName(e.target.value)}
                placeholder={view?.suggested || 'Ejemplo: NARIJ'}
              />
            </Field>
          </fieldset>
          <p className="declara-example">
            Ejemplo del nombre final: <code>{example}</code>
          </p>
          {view && (
            <p className="muted">
              {view.alta.fecha
                ? `Fecha de alta: ${longDate(view.alta.fecha)} (${view.alta.origen === 'Constancia' ? 'Constancia' : 'estimada del RFC'})`
                : 'Sin fecha de alta: todos los meses del ejercicio se evalúan.'}
              {view.suggested && !view.short_name_saved && ` · Nombre corto sugerido de la razón social.`}
            </p>
          )}
          {!state.companies.length && (
            <Link className="text-button" to="/empresas/nueva">
              Registrar una empresa para comenzar →
            </Link>
          )}
        </section>

        {mode === 'carpeta' && folderReady && company && (
          <FolderSource
            companyId={company}
            companyName={view?.name || ''}
            year={year}
            shortName={clean}
            ready={ready}
            lastRun={runs.find((r) => r.mode === 'carpeta' && r.year === year)}
            backup={folder.backup}
            poll={folder.poll}
            onBackup={folder.onBackup}
            onPoll={folder.onPoll}
            onAnalyzed={onOpenRun}
          />
        )}
        {mode === 'carpeta' && !company && (
          <section className={stitchCard + ' padded'}>
            <p className="muted">Elige la empresa para ver su carpeta vinculada.</p>
          </section>
        )}
        {mode === 'subir' && (
          <section
            className={stitchCard + ' padded declara-drop' + (dragging ? ' dragging' : '')}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={drop}
          >
            <Upload size={28} aria-hidden="true" />
            <strong>{busy ? 'Cargando PDF…' : 'Arrastra aquí los PDF o un ZIP'}</strong>
            <p className="muted">
              {ready ? 'El análisis empieza al soltar.' : 'Primero elige la empresa y el nombre corto.'}
            </p>
            <div className="actions">
              <button type="button" className={stitchButton} disabled={busy} onClick={() => docsRef.current?.click()}>
                <Upload size={16} />
                Seleccionar PDF
              </button>
              <button type="button" className={stitchButton} disabled={busy} onClick={() => folderRef.current?.click()}>
                <FolderOpen size={16} />
                Elegir carpeta
              </button>
              <button type="button" className={stitchButton} disabled={busy} onClick={() => zipRef.current?.click()}>
                <Archive size={16} />
                Cargar ZIP
              </button>
            </div>
            {files.length > 0 && !busy && (
              <div className="actions">
                <span className="muted">
                  {files.length} archivo(s) · {(files.reduce((n, f) => n + f.size, 0) / 1024 / 1024).toFixed(1)} MB
                </span>
                <button
                  type="button"
                  className={stitchPrimary}
                  disabled={!ready}
                  onClick={() => void onAnalyze(files).then(() => setFiles([]))}
                >
                  <RefreshCw size={16} />
                  Analizar
                </button>
              </div>
            )}
            {problem && <p className="declara-msg error">{problem}</p>}
            <small className="muted">
              Hasta 1,000 PDF y 100 MB por carga, o un ZIP de hasta 5,000 PDF y 500 MB descomprimidos. La carpeta se
              sube con su contenido directo; no se combinan subcarpetas.
            </small>
            {[zipRef, docsRef, folderRef].map((ref, i) => (
              <input
                key={i}
                ref={ref}
                hidden
                type="file"
                multiple={i !== 0}
                accept={i === 0 ? '.zip' : i === 1 ? '.pdf' : undefined}
                onChange={(e) => {
                  void take(e.target.files);
                  e.target.value = '';
                }}
              />
            ))}
          </section>
        )}

        <section className={stitchCard + ' padded'}>
          <div className="receipt-section-title">
            <h2>Control mensual {year}</h2>
            <Badge>Vista previa</Badge>
          </div>
          <MonthMatrix placeholder="Se llena al analizar" />
        </section>
      </div>

      <aside className="declara-step-side">
        <section className={stitchCard + ' padded declara-side-card'}>
          <h2>Sesión SAT</h2>
          {mode === 'carpeta' && folderReady ? (
            <FolderSat
              agentOnline={state.agent_link?.state === 'online'}
              machine={state.agent_link?.machine || ''}
              portal={!!agent?.capabilities.includes('sat_declaraciones')}
              lastRun={runs.find((r) => r.mode === 'carpeta' && r.year === year && r.status === 'analyzed')}
              onSat={folder.onSat}
            />
          ) : (
            <SatAccess
              state={state}
              company={company}
              shortName={clean}
              onRun={onOpenRun}
              notify={notify}
              refresh={refresh}
            />
          )}
        </section>
        <PreviousRuns runs={runs} onOpen={onOpenRun} busy={busy} />
      </aside>
    </div>
  );
}
