import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Building2, Clock3, ListChecks, ShieldCheck } from 'lucide-react';
import { api } from '../api';
import { dashboardUrl } from '../companyNavigation';
import { canRegisterCompanies } from '../permissions';
import type { State } from '../types';
import DocumentSummary, { riskTotals, saveSoon, savedSoon, type DocStatus } from './DocumentSummary';

const MONTHS = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
];
type Totals = { done: number; total: number; pending: number; overdue: number };

/** Tarjeta KPI clicable: el título es el enlace y cubre toda la tarjeta; los enlaces internos quedan encima. */
function KpiCard({
  label,
  to,
  icon,
  value,
  tone,
  detail,
  children,
}: {
  label: string;
  to: string;
  icon: ReactNode;
  value: ReactNode;
  tone: 'neutral' | 'amber' | 'red';
  detail: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className={'card kpi has-icon v2-kpi-link ' + tone}>
      <Link className="v2-kpi-stretch" to={to}>
        {label}
      </Link>
      <span className="kpi-icon">{icon}</span>
      <strong>{value}</strong>
      {children}
      <small>{detail}</small>
    </div>
  );
}

/** Dashboard principal › Resumen: las 4 tarjetas KPI y el semáforo documental. */
export default function DashboardSummary({
  state,
  period,
  companyId,
  notify,
}: {
  state: State;
  period: string;
  companyId?: string;
  notify: (m: string) => void;
}) {
  const user = state.current_user;
  const [soon, setSoon] = useState(() => savedSoon(user.id));
  const [docs, setDocs] = useState<DocStatus | null>(null);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [year, month] = period.split('-').map(Number);
  useEffect(() => {
    const abort = new AbortController();
    const q = new URLSearchParams({ soon: String(soon) });
    if (companyId) q.set('company_id', companyId);
    setError('');
    api<DocStatus>('/integral/document-status?' + q, 'GET', undefined, abort.signal)
      .then(setDocs)
      .catch((e) => !abort.signal.aborted && setError(e.message));
    return () => abort.abort();
  }, [soon, companyId, reload]);
  useEffect(() => {
    const abort = new AbortController();
    const q = new URLSearchParams({ year: String(year), month: String(month) });
    if (companyId) q.set('company_id', companyId);
    api<{ summary: Totals }>('/fiscal-control/checklist?' + q, 'GET', undefined, abort.signal)
      .then((d) => setTotals(d.summary))
      .catch(() => !abort.signal.aborted && setTotals(null));
    return () => abort.abort();
  }, [year, month, companyId, reload]);
  useEffect(() => {
    const update = () => setReload((n) => n + 1);
    window.addEventListener('contasuite-data-changed', update);
    return () => window.removeEventListener('contasuite-data-changed', update);
  }, []);
  const changeSoon = (days: number) => {
    setSoon(days);
    saveSoon(user.id, days);
  };
  const s = docs?.summary;
  const companies = s?.active_rfcs ?? 0;
  const sat = s?.sat ?? { positive: 0, negative: 0, none: 0, percent: 0 };
  const risk = s ? riskTotals(s) : { expired: 0, soon: 0, missing: 0 };
  const done = totals?.done ?? 0;
  const total = totals?.total ?? 0;
  const share = (n: number) => (companies ? (n / companies) * 100 + '%' : '0%');
  const opinions = (estado: string) => dashboardUrl('documentos', 'opiniones', { estado });
  return (
    <>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      <div className="v2-kpis" aria-label="Indicadores del periodo">
        <KpiCard
          label="Empresas activas"
          to={dashboardUrl('empresas', 'directorio')}
          icon={<Building2 size={18} aria-hidden />}
          value={companies}
          tone="neutral"
          detail={`${s?.physical ?? 0} físicas · ${s?.moral ?? 0} morales`}
        />
        <KpiCard
          label="Opinión SAT positiva"
          to={dashboardUrl('documentos', 'opiniones')}
          icon={<ShieldCheck size={18} aria-hidden />}
          value={
            <>
              {sat.positive} <small>de {companies}</small>
            </>
          }
          tone={sat.negative ? 'red' : 'neutral'}
          detail={
            <span className="v2-kpi-links">
              <Link to={opinions('positive')}>{sat.positive} positivas</Link> ·{' '}
              <Link to={opinions('negative')}>{sat.negative} negativas</Link> ·{' '}
              <Link to={opinions('none')}>{sat.none} sin opinión</Link>
            </span>
          }
        >
          <span className="v2-split-bar" aria-hidden>
            <Link to={opinions('positive')} tabIndex={-1} className="is-green" style={{ width: share(sat.positive) }} />
            <Link to={opinions('negative')} tabIndex={-1} className="is-red" style={{ width: share(sat.negative) }} />
            <Link to={opinions('none')} tabIndex={-1} className="is-gray" style={{ width: share(sat.none) }} />
          </span>
        </KpiCard>
        <KpiCard
          label={'Obligaciones de ' + MONTHS[month - 1]}
          to={dashboardUrl('obligaciones', 'matriz')}
          icon={<ListChecks size={18} aria-hidden />}
          value={
            <>
              {done} <small>de {total} hechas</small>
            </>
          }
          tone={totals?.overdue ? 'red' : 'neutral'}
          detail={
            total ? (
              `${totals!.pending} pendientes · ${totals!.overdue} vencidas`
            ) : canRegisterCompanies(user) ? (
              <span className="v2-kpi-links">
                <Link to="/empresas/nueva">Proponer obligaciones</Link> desde la Constancia de Situación Fiscal
              </span>
            ) : (
              'Sin obligaciones asignadas en el periodo'
            )
          }
        >
          <span className="v2-bar" role="img" aria-label={`${total ? Math.round((done / total) * 100) : 0}% hechas`}>
            <span style={{ width: (total ? (done / total) * 100 : 0) + '%' }} />
          </span>
        </KpiCard>
        <KpiCard
          label="Documentos en riesgo"
          to={dashboardUrl('documentos', 'semaforo', { estado: 'riesgo' })}
          icon={<Clock3 size={18} aria-hidden />}
          value={risk.expired + risk.soon}
          tone={risk.expired ? 'red' : risk.soon ? 'amber' : 'neutral'}
          detail={`${risk.expired} vencidos · ${risk.soon} por vencer`}
        />
      </div>
      {docs && (
        <DocumentSummary
          data={docs}
          soon={soon}
          onSoon={changeSoon}
          admin={user.admin}
          onSaved={() => setReload((n) => n + 1)}
          notify={notify}
        />
      )}
    </>
  );
}
