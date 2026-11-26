import { useEffect, useState } from 'react';
import { can } from '../permissions';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { Modal, Field } from '../components/ui';
import { stitchCard, stitchButton, stitchPrimary } from '../components/stitch';
import type { Summary } from './fiscalRead';
import type { State } from '../types';
type RecordRow = {
  id: string;
  company_id: string;
  obligation_id: string;
  effective_status: string;
  due_date: string | null;
  due_verified: boolean;
  revision: number;
  status: string;
  virtual_evidence?: { document_id: string; version_id: string }[];
};
type Report = {
  quality_total: number;
  alerts_total: number;
  lifecycle: {
    available: boolean;
    pending_alerts?: number;
    expiring_certificates?: number;
    expired_certificates?: number;
    upcoming_obligations?: number;
    overdue_obligations?: number;
    evidence_pending?: number | null;
    evidence_reason?: string;
    scope?: string;
  };
  company_counts: Record<string, number | null>;
  companies: { id: string; name: string }[];
  obligations: {
    summary: Summary | null;
    available: boolean;
    counts: Record<string, number> | null;
    verified_fulfilled: number | null;
    fulfilled_unverified: number | null;
    records: RecordRow[];
    catalog: { id: string; label: string }[];
  };
  certificates: {
    available: boolean;
    without_registered_certificate: number | null;
    records: {
      id: string;
      company_id: string;
      kind: string;
      state: string;
      days_remaining: number | null;
      valid_until: string | null;
      reviewed_at: string;
      origin: string;
    }[];
  };
  documents: {
    indexed: number;
    associated: number;
    pending: number;
    ambiguous: number;
    companies_without_documents: number;
    sources: { id: string; state: string; checked_at: string | null }[] | null;
    last_successful_scan: string | null;
    completeness_evaluated: boolean;
  };
  workload: { responsible: string; companies: number; pending: number; in_progress: number; completed_tasks: number }[];
  alerts: {
    id: string;
    company_id: string;
    source: string;
    reference: string;
    kind: string;
    priority: string;
    href: string;
  }[];
  quality: { company_id: string | null; source: string; reference: string; code: string }[];
  opinions: Opinion[];
  cfdi: Cfdi[];
};
type Opinion = {
  id: string;
  company_id: string;
  authority: string;
  consulted_on: string;
  result: string;
  next_review: string | null;
};
type Cfdi = {
  id: string;
  company_id: string;
  period: string;
  kind: string;
  reviewed_on: string;
  state: string;
  responsible: string;
};
export default function IntegralDashboard({
  state,
  period,
  view,
}: {
  state: State;
  period: string;
  /** Dashboard principal: Empresas › Calidad de datos, Documentos › Opiniones y Obligaciones › Seguimiento CFDI. */
  view: 'Calidad de datos' | 'Opiniones de cumplimiento' | 'Seguimiento CFDI';
}) {
  const [context, setContext] = useSearchParams();
  const [includeArchived, setIncludeArchived] = useState(false);
  const [data, setData] = useState<Report | null>(null),
    [company, setCompany] = useState(context.get('company_id') || ''),
    [regime, setRegime] = useState(''),
    [responsible, setResponsible] = useState(''),
    [reload, setReload] = useState(0),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(false),
    [form, setForm] = useState(false),
    [busy, setBusy] = useState(false);
  const [authority, setAuthority] = useState('SAT'),
    [result, setResult] = useState('unreviewed'),
    [date, setDate] = useState(''),
    [nextDate, setNextDate] = useState(''),
    [kind, setKind] = useState('issued');
  const [year, month] = period.split('-');
  useEffect(() => {
    setContext(
      (previous) => {
        const q = new URLSearchParams(previous);
        if (company) q.set('company_id', company);
        else q.delete('company_id');
        return q;
      },
      { replace: true },
    );
    // setContext changes identity on every URL change (React Router 7); as a dependency this URL sync
    // would re-run after its own write. It only has to follow the selected company.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [company]);
  useEffect(() => {
    const update = () => {
      if (document.visibilityState === 'visible') setReload((n) => n + 1);
    };
    window.addEventListener('focus', update);
    window.addEventListener('contasuite-data-changed', update);
    const timer = window.setInterval(update, 30000);
    return () => {
      window.removeEventListener('focus', update);
      window.removeEventListener('contasuite-data-changed', update);
      window.clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    const q = new URLSearchParams({ year, month, include_archived: String(includeArchived) });
    if (company) q.set('company_id', company);
    if (regime) q.set('regime', regime);
    if (responsible) q.set('responsible', responsible);
    api<Report>('/integral/dashboard?' + q)
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e) => {
        if (active) {
          setData(null);
          setError(e.message);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [year, month, company, regime, responsible, reload, includeArchived]);
  const name = (id: string) => state.companies.find((c) => c.id === id)?.name || 'Empresa';
  async function save() {
    if (!company || !date) return;
    setBusy(true);
    setError('');
    try {
      if (view === 'Opiniones de cumplimiento')
        await api('/integral/companies/' + company + '/opinions', 'POST', {
          authority,
          consulted_on: date,
          result,
          next_review: nextDate || null,
          responsible,
          notes: '',
        });
      else
        await api('/integral/companies/' + company + '/cfdi', 'POST', {
          period,
          kind,
          reviewed_on: date,
          state: result === 'positive' ? 'reviewed' : 'pending',
          incidents: '',
          responsible,
        });
      setForm(false);
      setReload((n) => n + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className={stitchCard + ' padded stitch-live-module integral-dashboard'}>
      <div className="card-title">
        <div>
          <h2>{view}</h2>
          <p>Período {period} · Registros internos; sin consultas automáticas a autoridades.</p>
        </div>
        <button className={stitchButton} onClick={() => setReload((n) => n + 1)}>
          Actualizar
        </button>
      </div>
      <div className="toolbar">
        <label>
          <input type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)} />
          Incluir archivadas en el resumen y selector
        </label>
        <select aria-label="Empresa del dashboard" value={company} onChange={(e) => setCompany(e.target.value)}>
          <option value="">Todas las empresas autorizadas</option>
          {state.companies
            .filter((c) => includeArchived || c.archived !== true || c.id === company)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
        </select>
        <select aria-label="Régimen del dashboard" value={regime} onChange={(e) => setRegime(e.target.value)}>
          <option value="">Todos los regímenes</option>
          {[...new Set(state.companies.map((c) => c.regime))].map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
        <select
          aria-label="Responsable del dashboard"
          value={responsible}
          onChange={(e) => setResponsible(e.target.value)}
        >
          <option value="">Todos los responsables</option>
          {/* The dashboard filters by the responsible's shown name, kept in step with the assigned user. */}
          {state.current_user.role === 'contador' && (
            <option value={state.current_user.display_name}>Mis empresas</option>
          )}
          {(state.responsibles || []).map((r) => (
            <option key={r.id} value={r.display_name}>
              {r.display_name + (r.enabled ? '' : ' (inactivo)')}
            </option>
          ))}
        </select>
      </div>
      {loading && <p role="status">Consultando datos…</p>}
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {data && (
        <>
          {view === 'Calidad de datos' && (
            <>
              <p>Incidencias de revisión, sin eliminación ni corrección automática.</p>
              <p>
                Se muestran hasta 200 incidencias de {data.quality_total}; consulta Documentos para revisar los
                registros.
              </p>
              {data.quality.slice(0, 200).map((q, i) => (
                <p key={i}>
                  {q.code} · {q.reference}{' '}
                  {q.company_id && (
                    <Link to={'/empresas/' + q.company_id + '/editar'}>Revisar {name(q.company_id)}</Link>
                  )}
                </p>
              ))}
            </>
          )}
          {view === 'Opiniones de cumplimiento' && (
            <>
              <button
                className={stitchPrimary}
                disabled={!company || !can(state.current_user, 'documentos.subir', company)}
                onClick={() => setForm(true)}
              >
                Registrar consulta manual
              </button>
              <p>No se presume una vigencia uniforme; la próxima revisión se configura por registro.</p>
              {data.opinions.map((o) => (
                <p key={o.id}>
                  {name(o.company_id)} · {o.authority} · {o.consulted_on} · {o.result} · Próxima revisión{' '}
                  {o.next_review || 'Sin configurar'}
                </p>
              ))}
            </>
          )}
          {view === 'Seguimiento CFDI' && (
            <>
              <button
                className={stitchPrimary}
                disabled={!company || !can(state.current_user, 'documentos.subir', company)}
                onClick={() => setForm(true)}
              >
                Registrar revisión manual
              </button>
              <p>La existencia de archivos no acredita que la facturación esté al día.</p>
              {data.cfdi.map((c) => (
                <p key={c.id}>
                  {name(c.company_id)} · {c.period} · {c.kind} · {c.state} · {c.reviewed_on}
                </p>
              ))}
            </>
          )}
        </>
      )}
      {form && (
        <Modal
          title={view}
          onClose={() => {
            if (!busy) setForm(false);
          }}
        >
          <div className="padded">
            <Field label="Fecha de consulta/revisión">
              <input required type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </Field>
            {view === 'Opiniones de cumplimiento' ? (
              <>
                <Field label="Autoridad">
                  <select value={authority} onChange={(e) => setAuthority(e.target.value)}>
                    {['SAT', 'IMSS', 'INFONAVIT'].map((a) => (
                      <option key={a}>{a}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Próxima revisión configurada">
                  <input type="date" value={nextDate} onChange={(e) => setNextDate(e.target.value)} />
                </Field>
              </>
            ) : (
              <Field label="Tipo de CFDI">
                <select value={kind} onChange={(e) => setKind(e.target.value)}>
                  {['issued', 'received', 'payroll'].map((k) => (
                    <option key={k}>{k}</option>
                  ))}
                </select>
              </Field>
            )}
            <Field label="Resultado/revisión">
              <select value={result} onChange={(e) => setResult(e.target.value)}>
                <option value="unreviewed">Sin revisar / pendiente</option>
                <option value="positive">Positiva / revisado</option>
                <option value="negative">Negativa</option>
                <option value="unavailable">No disponible</option>
              </select>
            </Field>
            <button className={stitchPrimary} disabled={busy || !date} onClick={() => void save()}>
              Guardar registro manual
            </button>
          </div>
        </Modal>
      )}
    </section>
  );
}
