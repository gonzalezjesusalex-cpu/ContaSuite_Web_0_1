import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Settings2 } from 'lucide-react';
import { api } from '../api';
import { stitchButton } from '../components/stitch';
import { dashboardUrl } from '../companyNavigation';
import { ICONS, STATE_TEXT, type CompanyLights, type Light } from './DocumentLights';
import './v11.css';

export type DocSummary = {
  active_rfcs: number;
  physical: number;
  moral: number;
  sat: { positive: number; negative: number; none: number; percent: number };
  expiring: {
    days: number;
    count: number;
    items: { company_id: string; name: string; kind: Light['kind']; expires: string }[];
  };
  states: Record<Light['kind'], Record<Light['state'], number>>;
};
export type Validity = Record<string, [number, number]>;
export type DocStatus = { companies: CompanyLights[]; summary: DocSummary; validity: Validity };

export const DOC_LABEL: Record<Light['kind'], string> = {
  fiel: 'FIEL',
  csf: 'Constancia de Situación Fiscal',
  sat: 'Opinión SAT',
  imss: 'Opinión IMSS',
  infonavit: 'Infonavit',
};
const VALIDITY_LABEL: Record<string, string> = {
  fiel: 'FIEL (días antes de vencer)',
  csf: 'Constancia de Situación Fiscal',
  sat: 'Opinión SAT',
  infonavit: 'Infonavit',
  imss: 'Opinión IMSS',
};
/** Filas y columnas del semáforo: documentos en su orden y estados por gravedad. */
export const DOC_KINDS: Light['kind'][] = ['fiel', 'csf', 'sat', 'imss', 'infonavit'];
export const SEVERITY_ORDER: Light['state'][] = ['red', 'amber', 'gray', 'green', 'na'];
export const SOON_CHOICES = [3, 7, 15, 30];

/** Vigencia bajo cada documento, leída de la configuración de vigencias (días de ámbar = plazo del documento). */
export function validityText(kind: Light['kind'], validity: Validity | undefined) {
  if (kind === 'fiel') return 'según certificado';
  const days = validity?.[kind]?.[1];
  const text = days === undefined ? '' : days <= 1 ? 'diaria' : `${days} días`;
  return kind === 'infonavit' ? [text, 'opcional'].filter(Boolean).join(' · ') : text;
}
/** Totales del bloque y de la tarjeta Documentos en riesgo: vencidos (rojo) y por vencer dentro del plazo elegido. */
export function riskTotals(s: DocSummary) {
  const count = (state: Light['state']) => DOC_KINDS.reduce((n, k) => n + (s.states[k]?.[state] ?? 0), 0);
  return { expired: count('red'), soon: s.expiring.count, missing: count('gray') };
}

/** «Por vencer en»: un solo valor por usuario, compartido por el semáforo y la tarjeta (preferencia del navegador). */
const soonKey = (userId: string) => 'contasuite-soon-days:' + userId;
export function savedSoon(userId: string) {
  try {
    const value = Number(localStorage.getItem(soonKey(userId)));
    return SOON_CHOICES.includes(value) ? value : 7;
  } catch {
    return 7;
  }
}
export function saveSoon(userId: string, days: number) {
  try {
    localStorage.setItem(soonKey(userId), String(days));
  } catch {
    /* sin almacenamiento: vuelve a 7 días al recargar */
  }
}

/** Plan v1.1 / Dashboard principal: semáforo documental del despacho como tabla (sin barras). */
export default function DocumentSummary({
  data,
  soon,
  onSoon,
  admin,
  onSaved,
  notify,
}: {
  data: DocStatus;
  soon: number;
  onSoon: (days: number) => void;
  admin: boolean;
  onSaved: () => void;
  notify: (s: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const s = data.summary;
  const totals = riskTotals(s);
  async function save(kind: string, green: number, amber: number) {
    try {
      await api('/integral/document-validity', 'PUT', { kind, green_days: green, amber_days: amber });
      onSaved();
    } catch (e) {
      notify((e as Error).message);
    }
  }
  return (
    <section className="card padded v11-summary v2-semaforo" aria-labelledby="semaforo-title">
      <div className="card-title">
        <div>
          <h2 id="semaforo-title">Semáforo documental</h2>
          <p className="muted">Según los documentos cargados; no consulta al SAT ni al IMSS.</p>
          <p className="v2-semaforo-totals">
            <span className={totals.expired ? 'is-red' : undefined}>{totals.expired} vencidos</span> ·{' '}
            <span>{totals.soon} por vencer</span> · <span>{totals.missing} sin documento</span>
          </p>
        </div>
        <div className="actions">
          <label className="v2-inline-field">
            Por vencer en
            <select aria-label="Por vencer en" value={soon} onChange={(e) => onSoon(Number(e.target.value))}>
              {SOON_CHOICES.map((d) => (
                <option key={d} value={d}>
                  {d} días
                </option>
              ))}
            </select>
          </label>
          {admin && (
            <button className={stitchButton} aria-pressed={editing} onClick={() => setEditing((v) => !v)}>
              <Settings2 size={16} aria-hidden /> Configurar vigencias
            </button>
          )}
        </div>
      </div>
      <div className="table-wrap">
        <table className="v2-semaforo-table">
          <caption className="sr-only">Estados del semáforo por documento</caption>
          <thead>
            <tr>
              <th scope="col">Documento</th>
              {SEVERITY_ORDER.map((st) => (
                <th scope="col" key={st} className={'is-' + st}>
                  {STATE_TEXT[st]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {DOC_KINDS.map((k) => {
              const Icon = ICONS[k];
              return (
                <tr key={k}>
                  <th scope="row">
                    <span className="v2-semaforo-doc">
                      <Icon size={15} aria-hidden />
                      <span>
                        {DOC_LABEL[k]}
                        <small>{validityText(k, data.validity)}</small>
                      </span>
                    </span>
                  </th>
                  {SEVERITY_ORDER.map((st) => {
                    const n = s.states[k]?.[st] ?? 0;
                    return (
                      <td key={st}>
                        {n === 0 ? (
                          <span className="v2-zero">0</span>
                        ) : (
                          <Link
                            className={st === 'na' ? 'v2-count-link' : 'v2-count is-' + st}
                            to={dashboardUrl('documentos', 'semaforo', { doc: k, estado: st })}
                            aria-label={`${n} ${DOC_LABEL[k]} en estado ${STATE_TEXT[st].toLowerCase()}`}
                          >
                            {n}
                          </Link>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {editing && (
        <div className="v11-validity">
          <p className="muted">
            Verde hasta N días desde la emisión; ámbar hasta M; después, rojo. Para la FIEL: ámbar cuando faltan M días
            o menos. Una opinión negativa siempre es roja.
          </p>
          {Object.entries(data.validity).map(([kind, [green, amber]]) => (
            <ValidityRow key={kind} kind={kind} green={green} amber={amber} onSave={save} />
          ))}
        </div>
      )}
    </section>
  );
}

function ValidityRow({
  kind,
  green,
  amber,
  onSave,
}: {
  kind: string;
  green: number;
  amber: number;
  onSave: (k: string, g: number, a: number) => void;
}) {
  const [g, setG] = useState(green);
  const [a, setA] = useState(amber);
  return (
    <div className="v11-validity-row">
      <span>{VALIDITY_LABEL[kind] || kind}</span>
      {kind !== 'fiel' && (
        <label>
          Verde hasta <input type="number" min={0} max={365} value={g} onChange={(e) => setG(Number(e.target.value))} />{' '}
          días
        </label>
      )}
      <label>
        {kind === 'fiel' ? 'Ámbar con' : 'Ámbar hasta'}{' '}
        <input type="number" min={0} max={365} value={a} onChange={(e) => setA(Number(e.target.value))} /> días
      </label>
      <button
        className={stitchButton}
        disabled={g === green && a === amber}
        onClick={() => onSave(kind, kind === 'fiel' ? a : g, a)}
      >
        Guardar
      </button>
    </div>
  );
}
