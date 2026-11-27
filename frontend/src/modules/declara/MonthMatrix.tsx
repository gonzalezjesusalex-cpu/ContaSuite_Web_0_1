import { Check, Download, X } from 'lucide-react';
import { Badge } from '../../components/ui';
import { stitchButton } from '../../components/stitch';
import { MONTHS, MONTH_STATES, monthLabel, shortDate, type Month, type MonthState } from './model';

function Mark({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={'declara-mark ' + (ok ? 'ok' : 'missing')}>
      {ok ? <Check size={14} aria-hidden="true" /> : <X size={14} aria-hidden="true" />}
      {label}
      <span className="sr-only">{ok ? ': disponible' : ': falta'}</span>
    </span>
  );
}

function extras(m: Month) {
  const list: string[] = [];
  if (m.complementarias) list.push(`+${m.complementarias} complementaria${m.complementarias > 1 ? 's' : ''}`);
  if (m.resico) list.push(`+${m.resico} RESICO`);
  if (m.salarios) list.push(`+${m.salarios} SALARIOS`);
  if (m.estado === 'VENCIDO') list.push(`Venció el ${shortDate(m.vence)}`);
  if (m.estado === 'POR_VENCER' || m.estado === 'EN_CURSO') list.push(`Vence el ${shortDate(m.vence)}`);
  return list;
}

/** Control mensual: 12 tarjetas. Sin datos (`months` vacío) se muestra en gris, «Se llena al analizar». */
export default function MonthMatrix({
  months,
  placeholder,
  onDownload,
}: {
  months?: Record<string, Month>;
  placeholder?: string;
  /** Modo carpeta con el SAT habilitado: «Descargar en SAT» en los meses exigibles incompletos. */
  onDownload?: (month: string) => void;
}) {
  const empty = !months || !Object.keys(months).length;
  return (
    <div className={'declara-matrix' + (empty ? ' placeholder' : '')}>
      <div className="declara-month-grid">
        {MONTHS.map((name, i) => {
          const m = months?.[name];
          const state = m ? MONTH_STATES[m.estado] : null;
          return (
            <article key={name} className={'declara-month ' + (m ? 'state-' + m.estado.toLowerCase() : 'empty')}>
              <header>
                <strong>
                  {i + 1}. {monthLabel(name)}
                </strong>
                {state && <Badge tone={state.tone}>{state.label}</Badge>}
              </header>
              {m ? (
                <>
                  <div className="declara-marks">
                    <Mark ok={m.declaracion} label="Declaración" />
                    <Mark ok={m.acuse} label="Acuse" />
                  </div>
                  {extras(m).length > 0 && (
                    <ul className="declara-extras">
                      {extras(m).map((e) => (
                        <li key={e}>{e}</li>
                      ))}
                    </ul>
                  )}
                  {onDownload && m.exigible && m.estado !== 'COMPLETO' && (
                    <button
                      type="button"
                      className={stitchButton + ' declara-month-sat'}
                      onClick={() => onDownload(name)}
                    >
                      <Download size={14} />
                      Descargar en SAT
                    </button>
                  )}
                </>
              ) : (
                <small className="muted">{placeholder || 'Se llena al analizar'}</small>
              )}
            </article>
          );
        })}
      </div>
      {!empty && (
        <ul className="declara-legend" aria-label="Leyenda de colores">
          {(Object.keys(MONTH_STATES) as MonthState[]).map((k) => (
            <li key={k}>
              <span className={'declara-dot ' + MONTH_STATES[k].tone} aria-hidden="true" />
              {MONTH_STATES[k].label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
