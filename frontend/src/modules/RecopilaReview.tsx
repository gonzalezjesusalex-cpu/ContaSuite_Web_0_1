import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, dateLabel } from '../api';

export type RecopilaPeriod = {
  period: string;
  run_id: string;
  policies: number;
  percent: number;
  parciales: number;
  xml_sin_pdf: number;
  sin_soporte: number;
  facturas_sin_poliza: number;
};
export type RecopilaPeriods = {
  periods: RecopilaPeriod[];
  pending: number;
  runs: { id: string; name: string; created_at: string; items: number }[];
};

const MONTHS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
export function periodLabel(period: string) {
  const [year, month] = period.split('-');
  return (MONTHS[Number(month) - 1] || month) + ' ' + year;
}

/** Support indicator of a company by period; `null` when the account cannot use Recopila (cambio 4.6). */
export function useRecopilaPeriods(companyId?: string, reload = 0) {
  const [data, setData] = useState<RecopilaPeriods | null>(null);
  useEffect(() => {
    setData(null);
    if (!companyId) return;
    const abort = new AbortController();
    api<RecopilaPeriods>('/recopila/companies/' + companyId + '/periods', 'GET', undefined, abort.signal)
      .then(setData)
      .catch(() => undefined);
    return () => abort.abort();
  }, [companyId, reload]);
  return data;
}

const link = (company: string, run: string) => '/recopilador-cfdi?empresa=' + company + '&analisis=' + run;

/** «Oct 2026: 92 % con soporte · 4 parciales · 11 facturas sin póliza», each one opening its analysis. */
export function RecopilaIndicator({ companyId, data }: { companyId: string; data: RecopilaPeriods | null }) {
  if (!data?.periods.length) return null;
  return (
    <ul className="recopila-indicator" aria-label="Soporte de pólizas por periodo (Recopila)">
      {data.periods.slice(0, 4).map((p) => (
        <li key={p.period}>
          <Link to={link(companyId, p.run_id)}>
            {periodLabel(p.period)}: {p.percent} % con soporte · {p.parciales} parciales · {p.facturas_sin_poliza}{' '}
            facturas sin póliza
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** Third section of «Por revisar»: analyses with items that still need a person (cambio 4.6). */
export function RecopilaReviewSection({ companyId, data }: { companyId: string; data: RecopilaPeriods | null }) {
  if (!data) return <p role="status">Consultando análisis de Recopila…</p>;
  const runs = data.runs.filter((r) => r.items > 0);
  return (
    <section aria-labelledby="recopila-review-title">
      <h3 id="recopila-review-title">Recopila</h3>
      <p>
        Pólizas parciales, sin soporte o con XML sin PDF, propuestas por aceptar y CFDI por revisar, según el último
        análisis de cada periodo. Una asociación no acredita cumplimiento fiscal.
      </p>
      {runs.length === 0 ? (
        <p className="muted">Sin pendientes de Recopila.</p>
      ) : (
        <ul>
          {runs.map((r) => (
            <li key={r.id}>
              <Link to={link(companyId, r.id)}>
                {r.name} · {dateLabel(r.created_at)}
              </Link>{' '}
              · {r.items} por revisar
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
