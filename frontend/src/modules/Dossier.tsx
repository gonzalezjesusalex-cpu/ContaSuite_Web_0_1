import { useState, useEffect } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import {
  Archive,
  ArrowLeft,
  Pencil,
  FolderInput,
  FolderOutput,
  FolderSearch,
  FileText,
  ShieldCheck,
  KeyRound,
} from 'lucide-react';
import { api, dateLabel, today } from '../api';
import { Badge, Kpi, Heading } from '../components/ui';
import { Records } from './Records';
import Documents from './Documents';
import CompanyDashboard from './CompanyDashboard';
import VirtualExplorer from './VirtualExplorer';
import Credentials from './Credentials';
import ArchiveActivity from './ArchiveActivity';
import CompanyHistory from './CompanyHistory';
import { ResponsibleDialog } from './ResponsibleSelect';
import { can, csfIsStale, responsibleName } from '../permissions';
import FiscalSummary from './FiscalSummary';
import FiscalControl from './FiscalControl';
import type { Company, Job, State } from '../types';
import { useLatestJob } from '../useLatestJob';
import { dossierSections, dossierSection, dossierUrl, directoryUrl } from '../companyNavigation';
import { confirmDiscard } from '../navigationGuard';
import { OriginalIcon } from '../components/OriginalIcon';
import { FolderAnalysisLine } from './FolderAnalysis';
import ExportDialog from './ExportDialog';
import CopyDialog from './CopyDialog';
import { CompanySwitcher, CompanyViews, MoreMenu } from './CompanyHeader';
export default function Dossier({
  company: c,
  state,
  refresh,
  notify,
}: {
  company: Company;
  state: State;
  refresh: () => Promise<void>;
  notify: (m: string) => void;
}) {
  const navigate = useNavigate();
  const [archiveError, setArchiveError] = useState('');
  const [params, setParams] = useSearchParams();
  const section = dossierSection(params.get('tab'));
  const legacy = params.get('tab');
  const tab =
    params.get('view') ||
    ([
      'Cumplimiento',
      'Histórico fiscal',
      'Credenciales y Certificados',
      'e.firma y CSD',
      'Explorador documental',
      'Tareas',
      'Historial',
      'Declaraciones',
    ].includes(legacy || '')
      ? legacy
      : null) ||
    {
      Resumen: 'Resumen',
      Obligaciones: 'Cumplimiento',
      Documentos: 'Documentos',
      'FIEL/CSD': 'Credenciales y Certificados',
      Actividad: 'Tareas',
    }[section] ||
    'Resumen';
  const period = /^20\d{2}-(0[1-9]|1[0-2])$/.test(params.get('period') || '')
    ? params.get('period')!
    : today().slice(0, 7);
  const tabs = dossierSections;
  const documentCount = state.document_counts[c.id] ?? 0;
  const tasks = state.tasks.filter((t) => t.company_id === c.id);
  const [busy, setBusy] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const me = state.current_user;
  const responsible = state.responsibles?.find((r) => r.id === c.accountant_id) || null;
  const allJobs = state.jobs.filter((j) => j.company_id === c.id);
  // The polled state only carries a summary of each result: «Análisis recientes» reads that list...
  const jobs = allJobs.filter((j) => j.kind === 'scan_folder');
  const [exporting, setExporting] = useState(false);
  const [copying, setCopying] = useState(false);
  // ...and the full results (the inventory) are those of this company's latest jobs of each kind.
  const scanJob = useLatestJob(state, c.id, 'scan_folder');
  const doneScan = useLatestJob(state, c.id, 'scan_folder', 'completed');
  const exportJob = useLatestJob(state, c.id, 'export_virtual', undefined, exporting);
  const dialogJobs = [scanJob, exportJob].filter((j): j is Job => !!j);
  // Why «Analizar carpeta» cannot run now, in plain words (Bloques 3 and 4): it uses the user's own linked agent;
  // the server also checks the folders the administrator authorizes and explains a refusal.
  const link = state.agent_link;
  const canScan = can(me, 'carpeta.analizar', c.id);
  // Keeping a copy of the content inside ContaSuite is an upload: it needs that permission as well.
  const canCopy = canScan && can(me, 'documentos.subir', c.id);
  const scanBlocked = !c.folder
    ? 'La empresa no tiene ruta de carpeta: agrégala en Editar › Expediente digital.'
    : link?.state === 'offline'
      ? 'Tu agente local está vinculado pero sin conexión' + (link.machine ? ' en ' + link.machine : '') + '.'
      : link?.state !== 'online'
        ? 'Tu agente local no está vinculado: abre ContaSuite en el equipo Windows donde se ejecuta el agente.'
        : link.roots === 0
          ? 'No hay carpetas autorizadas para el agente: las define la administración en Configuración.'
          : null;
  const lastFailure = jobs[0]?.status === 'failed' ? jobs[0].result.error || 'sin detalle' : null;
  const scanDone = doneScan?.result.summary ? doneScan : undefined;
  async function archiveCompany() {
    if (
      !confirmDiscard() ||
      !window.confirm(
        c.archived ? '¿Restaurar esta empresa?' : '¿Archivar sin eliminar documentos, relaciones ni permisos?',
      )
    )
      return;
    setBusy(true);
    setArchiveError('');
    try {
      await api('/company-lifecycle/' + c.id, 'PUT', { archived: !c.archived, revision: c.archive_revision || 0 });
      await refresh();
      notify(c.archived ? 'Empresa restaurada' : 'Empresa archivada');
    } catch (e) {
      setArchiveError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function view(value: string) {
    if (!confirmDiscard()) return;
    const q = new URLSearchParams(params);
    q.set('tab', section);
    q.set('view', value);
    q.delete('panel');
    q.set('period', period);
    setParams(q);
  }
  useEffect(() => {
    document.querySelector<HTMLElement>('.dossier-heading h1')?.focus();
  }, [c.id]);
  // While an analysis is queued or running, check every 3 s instead of waiting for the 60 s refresh.
  const scanning = allJobs.some((j) => j.status === 'queued' || j.status === 'running');
  useEffect(() => {
    if (!scanning) return;
    const timer = setInterval(() => void refresh().catch(() => undefined), 3000);
    return () => clearInterval(timer);
  }, [scanning, refresh]);
  async function scan() {
    setBusy(true);
    try {
      // The server uses the requester's own linked agent and explains any refusal (Bloque 4).
      await api('/jobs', 'POST', { company_id: c.id, kind: 'scan_folder' });
      await refresh();
      notify('Análisis enviado a tu agente' + (link?.machine ? ' en ' + link.machine : '') + '.');
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function showClassification() {
    if (!confirmDiscard()) return;
    const q = new URLSearchParams(params);
    q.set('tab', 'Documentos');
    q.set('view', 'Documentos');
    q.set('period', period);
    q.set('panel', 'clasificacion.' + Date.now());
    setParams(q);
  }
  const documentPanel = (
    <Documents
      key={c.id}
      companyId={c.id}
      notify={notify}
      refresh={refresh}
      analysisJob={scanJob}
      analysisDone={scanDone}
      onReanalyze={canScan ? () => void scan() : undefined}
      reanalyzeDisabled={busy || scanning || !!scanBlocked}
      analyzing={scanning}
      initialPanel={params.get('panel') || undefined}
    />
  );
  return (
    <>
      <div className="dossier-topbar">
        <Link className="back-link breadcrumb" to={directoryUrl(params)}>
          <ArrowLeft size={16} />
          Directorio de empresas
        </Link>
        <CompanySwitcher
          companies={state.companies}
          companyId={c.id}
          onChange={(id) => {
            if (confirmDiscard()) navigate(dossierUrl(id, section, period, params));
          }}
        />
      </div>
      <CompanyViews current="Expediente" companyId={c.id} period={period} context={params} />
      {c.archived && (
        <p className="error-banner" role="alert">
          Empresa archivada. Puedes registrar información con tus permisos habituales; guardar no restaura la empresa.
        </p>
      )}
      {!state.archive_available && <p role="status">Archivado pendiente de activar mediante migración autorizada.</p>}
      {archiveError && <p role="alert">{archiveError}</p>}
      <div className="dossier-heading">
        <div className="company-avatar big">{c.name.slice(0, 2).toUpperCase()}</div>
        <Heading
          title={c.name}
          description={`RFC: ${c.rfc} · Persona ${c.person_type} · ${c.regime}`}
          actions={
            // Each action by the role's permission in this company (Bloque 2), not by `admin` (Bloque 3).
            <div className="dossier-actions">
              {can(me, 'recibos.usar', c.id) && (
                <Link className="btn" to={'/recibos?empresa=' + c.id}>
                  <FileText size={16} />
                  Emitir recibo
                </Link>
              )}
              {canScan && (
                <button
                  className="btn primary"
                  disabled={busy || scanning || !!scanBlocked}
                  aria-describedby={scanBlocked ? 'scan-reason' : undefined}
                  onClick={scan}
                >
                  <FolderSearch size={17} />
                  {scanning ? 'Analizando…' : 'Analizar carpeta'}
                </button>
              )}
              {(can(me, 'recopila.usar', c.id) ||
                can(me, 'carpeta.exportar', c.id) ||
                canCopy ||
                can(me, 'empresa.editar', c.id) ||
                can(me, 'empresa.archivar', c.id)) && (
                <MoreMenu label="Más acciones de la empresa">
                  {can(me, 'recopila.usar', c.id) && (
                    <Link role="menuitem" to={'/recopilador-cfdi?empresa=' + c.id}>
                      <FolderSearch size={16} />
                      Recopila
                    </Link>
                  )}
                  {canCopy && (
                    <button role="menuitem" type="button" onClick={() => setCopying(true)}>
                      <FolderInput size={16} />
                      Guardar copia interna
                    </button>
                  )}
                  {can(me, 'carpeta.exportar', c.id) && (
                    <button role="menuitem" type="button" onClick={() => setExporting(true)}>
                      <FolderOutput size={16} />
                      Exportar copia ordenada
                    </button>
                  )}
                  {can(me, 'empresa.editar', c.id) && (
                    <Link role="menuitem" to={'/empresas/' + c.id + '/editar?' + params}>
                      <Pencil size={16} />
                      Editar
                    </Link>
                  )}
                  {can(me, 'empresa.archivar', c.id) && (
                    <button
                      role="menuitem"
                      type="button"
                      disabled={busy || !state.archive_available}
                      onClick={() => void archiveCompany()}
                    >
                      <Archive size={16} />
                      {c.archived ? 'Restaurar empresa' : 'Archivar empresa'}
                    </button>
                  )}
                </MoreMenu>
              )}
            </div>
          }
        />
      </div>
      {canScan && (scanBlocked || lastFailure) && (
        <p className="action-reason" id="scan-reason" role="status">
          {scanBlocked || 'El último análisis falló: ' + lastFailure}{' '}
          <Link to="/configuracion#agentes">Instrucciones del agente</Link>
        </p>
      )}
      <FolderAnalysisLine job={scanJob} doneJob={scanDone} onView={showClassification} />
      {copying && (
        <CopyDialog
          company={c}
          jobs={dialogJobs}
          agentReady={!scanBlocked}
          blockedReason={scanBlocked}
          refresh={refresh}
          notify={notify}
          onClose={() => setCopying(false)}
        />
      )}
      {exporting && (
        <ExportDialog
          company={c}
          jobs={dialogJobs}
          agentReady={!scanBlocked}
          blockedReason={scanBlocked}
          refresh={refresh}
          notify={notify}
          onClose={() => setExporting(false)}
        />
      )}
      <div className="dossier-meta">
        {c.is_demo && <Badge tone="blue">EMPRESA DEMO</Badge>}
        <Badge>Control fiscal por periodo</Badge>
        <span className="responsible-pill">
          <span className="company-avatar small" aria-hidden="true">
            {responsibleName(c, state.responsibles).slice(0, 1).toUpperCase()}
          </span>
          Responsable: {responsibleName(c, state.responsibles)}
          {me.admin && (
            <button
              type="button"
              className="link-button"
              aria-label="Cambiar contador responsable"
              onClick={() => setAssigning(true)}
            >
              Cambiar
            </button>
          )}
        </span>
        {!c.accountant_id && c.accountant_legacy && (
          <small className="muted">Texto anterior: {c.accountant_legacy}</small>
        )}
        <Badge>Sin consulta SAT</Badge>
        {csfIsStale(c) === true && (
          <Badge tone="amber">Constancia con más de 3 meses ({dateLabel(c.csf_issued_on!)})</Badge>
        )}
        {csfIsStale(c) === false && <Badge>Constancia del {dateLabel(c.csf_issued_on!)}</Badge>}
      </div>
      {assigning && (
        <ResponsibleDialog
          company={c}
          current={responsible}
          onClose={() => setAssigning(false)}
          onSaved={(notices) => {
            setAssigning(false);
            notices.forEach(notify);
            void refresh();
          }}
        />
      )}
      <div className="tabs card">
        {tabs.map((t) => (
          <button
            className={t === section ? 'active' : ''}
            onClick={() => {
              if (confirmDiscard()) {
                const q = new URLSearchParams(params);
                q.set('tab', t);
                q.set('period', period);
                q.delete('view');
                q.delete('panel');
                setParams(q);
              }
            }}
            key={t}
          >
            {t === 'Declaraciones' && <OriginalIcon name="declaraciones" size={24} />}
            <span className="tab-label">{t}</span>
            {t === 'Documentos' && <span>{documentCount}</span>}
          </button>
        ))}
      </div>
      {section === 'Resumen' && <FiscalSummary period={period} companyId={c.id} compact />}
      {section === 'Actividad' && <ArchiveActivity companyId={c.id} available={!!state.archive_available} />}
      <div className="actions" aria-label="Vistas de la sección">
        {(section === 'Obligaciones'
          ? ['Cumplimiento', 'Histórico fiscal']
          : section === 'Documentos'
            ? ['Documentos', 'Explorador documental']
            : section === 'FIEL/CSD'
              ? ['Credenciales y Certificados', 'e.firma y CSD']
              : section === 'Actividad'
                ? ['Tareas', 'Historial', ...(can(me, 'declara.usar', c.id) ? ['Declaraciones'] : [])]
                : []
        ).map((v) => (
          <button className="btn" aria-pressed={tab === v} key={v} onClick={() => view(v)}>
            {v}
          </button>
        ))}
      </div>
      {tab === 'Explorador documental' ? (
        <VirtualExplorer
          companyId={c.id}
          admin={state.current_user.admin}
          notify={notify}
          refresh={refresh}
          job={scanDone}
        />
      ) : tab === 'Credenciales y Certificados' ? (
        <Credentials state={state} companyId={c.id} />
      ) : tab === 'Declaraciones' && can(me, 'declara.usar', c.id) ? (
        <section className="card padded">
          <h2>Declaraciones y acuses</h2>
          <p className="muted">
            Analiza los PDF de esta empresa, revisa sus nombres y consulta el control mensual en Declara.
          </p>
          <div className="actions">
            <Link className="btn primary" to={'/declara?empresa=' + c.id}>
              <FileText size={16} />
              Abrir Declara
            </Link>
          </div>
        </section>
      ) : tab === 'Cumplimiento' ? (
        <FiscalControl state={state} period={period} companyId={c.id} notify={notify} />
      ) : tab === 'Histórico fiscal' ? (
        <FiscalSummary period={period} companyId={c.id} />
      ) : tab === 'Tareas' ? (
        <Records kind="tasks" state={state} companyId={c.id} refresh={refresh} notify={notify} />
      ) : tab === 'Documentos' ? (
        documentPanel
      ) : tab === 'e.firma y CSD' ? (
        <>
          <CompanyDashboard companyId={c.id} notify={notify} canWrite={(cid) => can(me, 'documentos.subir', cid)} />
          <div className="card">
            <div className="card-title">
              <div>
                <h2>
                  <KeyRound size={19} /> e.firma y CSD
                </h2>
                <p>
                  La vigencia temporal se interpreta a partir del CER público. La validación ante el SAT permanece
                  pendiente.
                </p>
              </div>
              <Badge tone="amber">Validación SAT pendiente</Badge>
            </div>
            <div className="info-box">
              <ShieldCheck size={22} />
              <p>
                No se capturan contraseñas ni se suben llaves privadas en esta versión. Puedes adjuntar certificados
                públicos .cer en Documentos; sus fechas y RFC se muestran en el seguimiento superior.
              </p>
            </div>
          </div>
        </>
      ) : tab === 'Historial' ? (
        <CompanyHistory companyId={c.id} />
      ) : (
        <>
          <div className="kpi-grid four">
            <Kpi label="Documentos adjuntos" value={documentCount} detail="Sin validación automática" tone="blue" />
            <Kpi
              label="Tareas abiertas"
              value={tasks.filter((t) => t.status !== 'Completada').length}
              detail="Seguimiento operativo"
            />
            <Kpi
              label="Tareas vencidas"
              value={tasks.filter((t) => t.status !== 'Completada').filter((t) => t.due_date < today()).length}
              detail="Según fechas capturadas"
              tone="red"
            />
          </div>
          <div className="dossier-detail-grid">
            <div className="card padded">
              <h2>Información del contribuyente</h2>
              <dl>
                {[
                  ['RFC', c.rfc],
                  ['idCIF', c.idcif],
                  ...(c.person_type === 'Física' ? [['CURP', c.curp]] : []),
                  ['Nombre comercial', c.trade_name],
                  ['Tipo de persona', c.person_type],
                  ['Regímenes vigentes', (c.regimes || []).map((r) => r.label).join('; ') || c.regime],
                  ['Inicio de operaciones', c.operations_start ? dateLabel(c.operations_start) : ''],
                  ['Estatus en el padrón', c.padron_status],
                  ['Domicilio fiscal', fiscalAddress(c)],
                  ['Constancia emitida', c.csf_issued_on ? dateLabel(c.csf_issued_on) : ''],
                  ['Contador', responsibleName(c, state.responsibles)],
                  ['Correo', c.email],
                  ['Teléfono', c.phone],
                  ['Ubicación', c.location],
                ].map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{v || 'Sin capturar'}</dd>
                  </div>
                ))}
              </dl>
              <h3>Notas internas</h3>
              <p className="notes">{c.notes || 'Sin observaciones.'}</p>
            </div>
            <div className="card padded">
              <h2>Carpeta del servidor / equipo local</h2>
              <p className="path-text folder-path">{c.folder || 'Sin ruta configurada'}</p>
              <p className="muted">
                El agente lista nombres y tamaños de PDF, XML y CER públicos en las rutas autorizadas. Excluye claves y
                secretos. Este análisis no importa por sí solo el catálogo documental.
              </p>
              <p className="muted">
                {link?.state === 'online'
                  ? 'Se usará tu agente' + (link.machine ? ' en ' + link.machine : '') + ', con tus permisos.'
                  : 'Se usará tu agente vinculado cuando esté en línea.'}
              </p>
              <button className="btn" disabled={busy || !canScan || !!scanBlocked} onClick={scan}>
                <FolderSearch size={16} />
                Analizar expediente
              </button>
              <h3 className="section-subtitle">Análisis recientes</h3>
              {jobs.length ? (
                jobs.slice(0, 3).map((j) => (
                  <div className="job-result" key={j.id}>
                    <div>
                      <strong>
                        {
                          (
                            {
                              queued: 'En cola',
                              running: 'Procesando',
                              completed: 'Completado',
                              failed: 'Fallido',
                            } as Record<string, string>
                          )[j.status]
                        }
                      </strong>
                      <small>{dateLabel(j.created_at)}</small>
                    </div>
                    {j.result.error && <p className="red-text">{j.result.error}</p>}
                    {(j.result.total !== undefined || j.result.summary || j.result.files) && (
                      <p>
                        {(j.result.total ?? j.result.summary?.total ?? j.result.files?.length ?? 0).toLocaleString(
                          'es-MX',
                        )}{' '}
                        archivos clasificados{j.result.truncated && ' · Se alcanzó el límite de escaneo'}
                      </p>
                    )}
                    {j.result.warnings?.map((w, i) => (
                      <p className="muted" key={i}>
                        {w}
                      </p>
                    ))}
                  </div>
                ))
              ) : (
                <p className="muted">Sin análisis realizados.</p>
              )}
            </div>
          </div>
          {documentPanel}
        </>
      )}
    </>
  );
}

/** Fiscal address of the constancia in one line, skipping empty parts (Bloque 1). */
function fiscalAddress(c: Company) {
  const street = [
    c.tax_street_type,
    c.tax_street,
    c.tax_exterior_number,
    c.tax_interior_number && 'int. ' + c.tax_interior_number,
  ]
    .filter(Boolean)
    .join(' ');
  return [street, c.tax_neighborhood, c.tax_postal_code && 'C.P. ' + c.tax_postal_code, c.tax_municipality, c.tax_state]
    .filter(Boolean)
    .join(', ');
}
