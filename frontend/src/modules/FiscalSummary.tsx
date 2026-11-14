import { Kpi } from '../components/ui';
import { useFiscalRead } from './fiscalRead';
export default function FiscalSummary({
  period,
  companyId,
  compact = false,
}: {
  period: string;
  companyId: string;
  /** One low row of four figures, for the dossier's «Resumen» (Bloque 3). */
  compact?: boolean;
}) {
  const { data, error } = useFiscalRead(period, companyId);
  if (compact)
    return (
      <section className="card fiscal-strip stitch-live-module" aria-label={'Resumen fiscal ' + period}>
        <h2>Resumen fiscal · {period}</h2>
        {error ? (
          <p role="alert">{error}</p>
        ) : !data ? (
          <p role="status">Consultando control fiscal…</p>
        ) : (
          <>
            <dl>
              {[
                [
                  'Universo fiscal',
                  data.summary.universe,
                  `${data.summary.registered} registradas · ${data.summary.implicit} implícitas`,
                ],
                ['Sin revisar', data.summary.counts.unreviewed, `de ${data.summary.universe} celdas`],
                ['Vencidas confirmadas', data.summary.counts.overdue, 'solo fechas verificadas'],
                [
                  'Cumplidas verificadas',
                  data.summary.verified_fulfilled,
                  `de ${data.summary.denominators.verification} registradas`,
                ],
              ].map(([label, value, detail]) => (
                <div key={String(label)}>
                  <dt>{label}</dt>
                  <dd>
                    <strong>{value}</strong>
                    <small>{detail}</small>
                  </dd>
                </div>
              ))}
            </dl>
            <Historical data={data} />
          </>
        )}
      </section>
    );
  return (
    <section className="card padded stitch-live-module">
      <h2>Resumen fiscal · {period}</h2>
      {error ? (
        <p role="alert">{error}</p>
      ) : !data ? (
        <p role="status">Consultando control fiscal…</p>
      ) : (
        <>
          <div className="kpi-grid four">
            <Kpi
              label="Universo fiscal"
              value={data.summary.universe}
              detail={`${data.summary.registered} registradas · ${data.summary.implicit} implícitas`}
            />
            <Kpi
              label="Sin revisar"
              value={data.summary.counts.unreviewed}
              detail={`De ${data.summary.universe} celdas`}
            />
            <Kpi label="Vencidas confirmadas" value={data.summary.counts.overdue} detail="Solo fechas verificadas" />
            <Kpi
              label="Cumplidas verificadas"
              value={data.summary.verified_fulfilled}
              detail={`De ${data.summary.denominators.verification} cumplidas registradas`}
            />
          </div>
          <Historical data={data} />
        </>
      )}
    </section>
  );
}

function Historical({ data }: { data: NonNullable<ReturnType<typeof useFiscalRead>['data']> }) {
  return (
    <details>
      <summary>Históricos del periodo y pendientes de conciliación ({data.historical.length})</summary>
      <p>Fuera de los indicadores canónicos. Valores originales, sin verificación inferida.</p>
      {data.historical.map((r) => (
        <article key={r.id}>
          <strong>
            {r.title} · {r.period} · {r.status}
          </strong>
          <p>
            {r.period_reliable ? 'Periodo registrado' : 'Periodo ambiguo'} · Referencia:{' '}
            {r.reference || 'Sin referencia'}
          </p>
          <p style={{ whiteSpace: 'pre-wrap' }}>{r.notes}</p>
        </article>
      ))}
    </details>
  );
}
