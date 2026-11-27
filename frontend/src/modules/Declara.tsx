import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ArrowRight, RefreshCw } from 'lucide-react';
import { api, getToken } from '../api';
import { Badge, Heading, Kpi } from '../components/ui';
import { stitchButton, stitchCard, stitchPrimary } from '../components/stitch';
import type { State } from '../types';
import MonthMatrix from './declara/MonthMatrix';
import PdfTable from './declara/PdfTable';
import ResolveDrawer from './declara/ResolveDrawer';
import StepApply from './declara/StepApply';
import StepSource, { type Mode } from './declara/StepSource';
import Stepper, { type Step } from './declara/Stepper';
import { RUN_LABELS, longDate, type CompanyView, type Detail, type Run } from './declara/model';

const WORKING = ['analyzing', 'editing', 'generating'];

export default function Declara({
  state,
  notify,
  refresh,
}: {
  state: State;
  notify: (m: string) => void;
  refresh: () => Promise<void>;
}) {
  const [params] = useSearchParams();
  const thisYear = new Date().getFullYear();
  const [company, setCompany] = useState(state.companies.find((c) => c.id === params.get('empresa'))?.id || '');
  const [year, setYear] = useState(thisYear);
  const [shortName, setShortName] = useState('');
  const [view, setView] = useState<CompanyView | null>(null);
  const [mode, setMode] = useState<Mode>('subir');
  const [runs, setRuns] = useState<Run[]>([]);
  const [id, setId] = useState('');
  const [detail, setDetail] = useState<Detail | null>(null);
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [logVersion, setLogVersion] = useState(0);
  const status = detail?.run.status || '';
  const working = busy || WORKING.includes(status);

  // Datos de Declara de la empresa: nombre corto guardado (o sugerido), modo preferido y fecha de alta.
  useEffect(() => {
    setView(null);
    if (!company) {
      setShortName('');
      return;
    }
    let active = true;
    api<CompanyView>('/declara/companies/' + encodeURIComponent(company))
      .then((v) => {
        if (!active) return;
        setView(v);
        setShortName(v.short_name);
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [company]);

  useEffect(() => {
    if (!company) {
      setRuns([]);
      return;
    }
    let active = true;
    api<Run[]>('/declara/runs?company_id=' + encodeURIComponent(company))
      .then((r) => active && setRuns(r))
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [company, reload]);

  useEffect(() => {
    if (!id) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const d = await api<Detail>('/declara/runs/' + id);
        if (!active) return;
        setDetail(d);
        if (WORKING.includes(d.run.status)) timer = setTimeout(load, 1200);
        else {
          setLogVersion((v) => v + 1);
          refresh().catch(() => undefined);
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    }
    load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [id, reload, refresh]);

  const openRun = useCallback(
    (next: string) => {
      setId(next);
      setDetail(null);
      setSelected(null);
      setError('');
      setStep(next ? 2 : 1);
      if (next) {
        const run = runs.find((r) => r.id === next);
        if (run?.year) setYear(run.year);
      }
    },
    [runs],
  );

  function changeCompany(next: string) {
    setCompany(next);
    openRun('');
  }

  async function analyze(files: File[]) {
    setError('');
    setBusy(true);
    try {
      const form = new FormData();
      form.append('company_id', company);
      form.append('short_name', shortName);
      form.append('year', String(year));
      for (const f of files) form.append('files', f, f.webkitRelativePath || f.name);
      const run = await api<Run>('/declara/runs', 'POST', form);
      openRun(run.id);
      setDetail({ run, records: [] });
      setReload((v) => v + 1);
      notify('PDF cargados. Comenzó el análisis de Declara.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function changeMode(next: Mode) {
    setMode(next);
    if (company) api('/declara/companies/' + encodeURIComponent(company), 'PUT', { mode: next }).catch(() => undefined);
  }

  async function generate() {
    if (!detail) return;
    setError('');
    setBusy(true);
    try {
      await api('/declara/runs/' + id + '/generate', 'POST', { revision: detail.run.revision });
      setDetail((d) =>
        d ? { ...d, run: { ...d.run, status: 'generating', message: 'Aplicando nombres en copias verificadas…' } } : d,
      );
      setReload((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
      setReload((v) => v + 1);
    } finally {
      setBusy(false);
    }
  }

  async function undo(index: number) {
    if (!detail) return;
    setBusy(true);
    try {
      const d = await api<Detail>(`/declara/runs/${id}/resolve`, 'POST', {
        revision: detail.run.revision,
        index,
        action: 'undo',
      });
      setDetail(d);
      setLogVersion((v) => v + 1);
      notify('Cambio manual deshecho.');
    } catch (e) {
      setError((e as Error).message);
      setReload((v) => v + 1);
    } finally {
      setBusy(false);
    }
  }

  async function download(kind: 'zip' | 'csv') {
    setBusy(true);
    setError('');
    try {
      const response = await fetch('/api/declara/runs/' + id + '/download?kind=' + kind, {
        headers: { Authorization: 'Bearer ' + getToken() },
      });
      if (!response.ok) throw new Error('No se pudo descargar el resultado.');
      const blob = await response.blob();
      if (!blob.size) throw new Error('La descarga llegó vacía. No se guardó ningún archivo. Vuelve a intentarlo.');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `DECLARA_${detail?.run.expected_rfc}.${kind}`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1500);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const reviewable = !!detail && !['analyzing', 'error'].includes(status) && detail.records.length > 0;
  const generated = status === 'generated';
  const runMode = (detail?.run.mode as Mode) || mode;
  const steps: Step[] = [
    { n: 1, label: 'Empresa y PDF', state: step === 1 ? 'current' : detail ? 'done' : 'available' },
    {
      n: 2,
      label: 'Revisión y meses',
      state: !reviewable ? 'locked' : step === 2 ? 'current' : step === 3 ? 'done' : 'available',
    },
    {
      n: 3,
      label: runMode === 'carpeta' ? 'Aplicar y auditoría' : 'Copias y auditoría',
      state: !reviewable
        ? 'locked'
        : generated
          ? step === 3
            ? 'current'
            : 'done'
          : step === 3
            ? 'current'
            : 'available',
    },
  ];
  const s = detail?.run.summary || {};
  const activeYear = String(s.year || detail?.run.year || year);
  const months = detail?.run.months?.[activeYear];
  const record = detail?.records.find((r) => r.index === selected) || null;
  const companyName = state.companies.find((c) => c.id === (detail?.run.company_id || company));

  return (
    <div className="declara-module stitch-live-module">
      <Heading
        eyebrow="CONTROL DOCUMENTAL"
        title="Declara"
        description="Analiza declaraciones y acuses del SAT, revisa sus nombres y lleva el control mensual por empresa."
      />
      <Stepper steps={steps} onSelect={setStep} />
      {error && (
        <div className="error-banner" role="alert">
          {error}
          <button onClick={() => setError('')}>Cerrar</button>
          {id && (
            <button disabled={busy} onClick={() => setReload((v) => v + 1)}>
              Actualizar análisis
            </button>
          )}
        </div>
      )}
      {detail && step !== 1 && (
        <div className="declara-run-head">
          <div>
            <strong>
              {detail.run.short_name} · {detail.run.expected_rfc}
            </strong>
            <span>
              {companyName?.name} · Ejercicio {activeYear}
              {s.alta?.fecha &&
                ` · Fecha de alta: ${longDate(s.alta.fecha)} (${s.alta.origen === 'Constancia' ? 'Constancia' : 'estimada del RFC'})`}
            </span>
          </div>
          <div className="recopila-status" role="status">
            {WORKING.includes(status) && <RefreshCw size={16} className="recopila-spinner" />}
            <Badge tone={status === 'error' ? 'red' : generated ? 'green' : 'blue'}>
              {RUN_LABELS[status] || status}
            </Badge>
            <span>{detail.run.message}</span>
          </div>
        </div>
      )}

      {step === 1 && (
        <StepSource
          state={state}
          company={company}
          onCompany={changeCompany}
          year={year}
          onYear={setYear}
          shortName={shortName}
          onShortName={setShortName}
          view={view}
          mode={mode}
          onMode={changeMode}
          runs={runs}
          busy={busy}
          onAnalyze={analyze}
          onOpenRun={openRun}
          notify={notify}
          refresh={refresh}
        />
      )}

      {step !== 1 && detail && !reviewable && (
        <section className={stitchCard + ' padded'}>
          <p>{status === 'error' ? detail.run.message : 'Analizando los PDF…'}</p>
          <button type="button" className={stitchButton} onClick={() => openRun('')}>
            Volver a Empresa y PDF
          </button>
        </section>
      )}

      {step === 2 && detail && reviewable && (
        <>
          {detail.run.warnings.map((w, i) => (
            <p className="recopila-warning" key={i}>
              {w}
            </p>
          ))}
          <div className="kpi-grid six declara-kpis">
            <Kpi label="PDF analizados" value={s.total ?? '—'} detail="Archivos directos" />
            <Kpi label="Por renombrar" value={s.rename ?? '—'} detail="Nombres del plan" tone="blue" />
            <Kpi label="Correctos" value={s.correct ?? '—'} detail="Ya con nombre estándar" tone="green" />
            <Kpi label="Copias idénticas" value={s.identical ?? '—'} detail="Misma huella; no se copian" />
            <Kpi
              label="Omitidos o con error"
              value={(s.omitted ?? 0) + (s.rfc_other ?? 0)}
              detail="Revísalos con «Resolver»"
              tone="amber"
            />
            <Kpi
              label="RFC"
              value={s.rfc_matches ? '✓' : '!'}
              detail={
                s.rfc_matches
                  ? 'Coincide con la empresa'
                  : `Detectado ${s.primary_rfc || 'sin RFC'}: no coincide con la empresa`
              }
              tone={s.rfc_matches ? 'green' : 'red'}
            />
          </div>
          <section className={stitchCard + ' padded'}>
            <div className="receipt-section-title">
              <h2>Control mensual {activeYear}</h2>
              <small className="muted">
                Un mes se completa con declaración normal y acuse normal. Vence el día {s.due_day || 17} del mes
                siguiente. Seguimiento documental: no acredita cumplimiento ante el SAT.
              </small>
            </div>
            {months ? (
              <MonthMatrix months={months} />
            ) : (
              <MonthMatrix placeholder="Sin control: el RFC no coincide con la empresa" />
            )}
          </section>
          <section className={stitchCard + ' padded'}>
            <div className="receipt-section-title">
              <h2>PDF analizados</h2>
              <button type="button" className={stitchPrimary} onClick={() => setStep(3)}>
                Continuar a {steps[2].label.toLowerCase()}
                <ArrowRight size={16} />
              </button>
            </div>
            <PdfTable
              records={detail.records}
              generated={generated}
              editable={status === 'analyzed'}
              busy={working}
              onOpen={setSelected}
              onUndo={undo}
            />
          </section>
        </>
      )}

      {step === 3 && detail && reviewable && (
        <StepApply detail={detail} busy={working} logVersion={logVersion} onGenerate={generate} onDownload={download} />
      )}

      {record && detail && (
        <ResolveDrawer
          key={record.index + ':' + detail.run.revision}
          runId={id}
          revision={detail.run.revision}
          editable={status === 'analyzed'}
          record={record}
          records={detail.records}
          onClose={() => setSelected(null)}
          onApplied={(d, message) => {
            setDetail(d);
            setSelected(null);
            setLogVersion((v) => v + 1);
            notify(message);
          }}
        />
      )}
    </div>
  );
}
