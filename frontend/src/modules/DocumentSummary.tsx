import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { Kpi } from '../components/ui';
import { stitchButton } from '../components/stitch';
import { ICONS, STATE_TEXT, type CompanyLights, type Light } from './DocumentLights';
import './v11.css';

type Summary = {
  active_rfcs: number;
  physical: number;
  moral: number;
  sat: { positive: number; negative: number; none: number; percent: number };
  expiring: { days: number; count: number; items: { company_id: string; name: string; kind: Light['kind']; expires: string }[] };
  states: Record<Light['kind'], Record<Light['state'], number>>;
};
type Validity = Record<string, [number, number]>;
const LABEL: Record<string, string> = {
  fiel: 'FIEL (días antes de vencer)',
  csf: 'Constancia de Situación Fiscal',
  sat: 'Opinión SAT',
  infonavit: 'Infonavit',
  imss: 'Opinión IMSS',
};
const KINDS: Light['kind'][] = ['fiel', 'csf', 'sat', 'infonavit', 'imss'];

/** Plan v1.1: summary cards of the document traffic light for the office dashboard. */
export default function DocumentSummary({ admin, notify }: { admin: boolean; notify: (s: string) => void }) {
  const [soon, setSoon] = useState(7);
  const [data, setData] = useState<{ companies: CompanyLights[]; summary: Summary; validity: Validity } | null>(null);
  const [editing, setEditing] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    api<{ companies: CompanyLights[]; summary: Summary; validity: Validity }>('/integral/document-status?soon=' + soon)
      .then(setData)
      .catch(() => setData(null));
  }, [soon, reload]);
  if (!data) return null;
  const s = data.summary;
  async function save(kind: string, green: number, amber: number) {
    try {
      await api('/integral/document-validity', 'PUT', { kind, green_days: green, amber_days: amber });
      setReload((n) => n + 1);
    } catch (e) {
      notify((e as Error).message);
    }
  }
  return (
    <section className="card padded v11-summary">
      <div className="card-title">
        <div>
          <h3>Semáforo documental</h3>
          <p className="muted">Vigencias del despacho · lecturas de documentos, sin consulta a autoridades.</p>
        </div>
        <div className="actions">
          <label>
            Por vencer en{' '}
            <select aria-label="Días para por vencer" value={soon} onChange={(e) => setSoon(Number(e.target.value))}>
              {[3, 7, 15, 30].map((d) => (
                <option key={d} value={d}>
                  {d} días
                </option>
              ))}
            </select>
          </label>
          {admin && (
            <button className={stitchButton} aria-pressed={editing} onClick={() => setEditing((v) => !v)}>
              Vigencias
            </button>
          )}
        </div>
      </div>
      <div className="kpi-grid four">
        <Kpi label="RFC activos" value={s.active_rfcs} detail={`${s.physical} personas físicas · ${s.moral} morales`} tone="blue" />
        <Kpi
          label="Opinión de cumplimiento SAT"
          value={s.sat.percent + '% positivas'}
          detail={`${s.sat.positive} positivas · ${s.sat.negative} negativas · ${s.sat.none} sin opinión`}
          tone={s.sat.negative ? 'red' : 'green'}
        />
        <Kpi
          label="Documentos por vencer"
          value={s.expiring.count}
          detail={`En los próximos ${s.expiring.days} días`}
          tone={s.expiring.count ? 'amber' : 'green'}
        />
      </div>
      <div className="v11-state-grid" role="table" aria-label="Estados del semáforo por documento">
        <div role="row" className="v11-state-head">
          <span role="columnheader">Documento</span>
          {(['green', 'amber', 'red', 'gray', 'na'] as const).map((st) => (
            <span role="columnheader" key={st} className={'is-' + st}>
              {STATE_TEXT[st]}
            </span>
          ))}
        </div>
        {KINDS.map((k) => {
          const Icon = ICONS[k];
          return (
            <div role="row" key={k}>
              <span role="rowheader">
                <Icon size={15} aria-hidden /> {LABEL[k].replace(' (días antes de vencer)', '')}
              </span>
              {(['green', 'amber', 'red', 'gray', 'na'] as const).map((st) => (
                <span role="cell" key={st}>
                  {s.states[k]?.[st] ?? 0}
                </span>
              ))}
            </div>
          );
        })}
      </div>
      {s.expiring.items.length > 0 && (
        <details>
          <summary>Ver documentos por vencer</summary>
          <ul>
            {s.expiring.items.map((e) => (
              <li key={e.company_id + e.kind}>
                <Link to={'/empresas/' + e.company_id}>{e.name}</Link> · {LABEL[e.kind].replace(' (días antes de vencer)', '')} ·{' '}
                {new Date(e.expires + 'T12:00:00').toLocaleDateString('es-MX')}
              </li>
            ))}
          </ul>
        </details>
      )}
      {editing && (
        <div className="v11-validity">
          <p className="muted">
            Verde hasta N días desde la emisión; ámbar hasta M; después, rojo. Para la FIEL: ámbar cuando faltan M días o
            menos. Una opinión negativa siempre es roja.
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
      <span>{LABEL[kind] || kind}</span>
      {kind !== 'fiel' && (
        <label>
          Verde hasta <input type="number" min={0} max={365} value={g} onChange={(e) => setG(Number(e.target.value))} /> días
        </label>
      )}
      <label>
        {kind === 'fiel' ? 'Ámbar con' : 'Ámbar hasta'}{' '}
        <input type="number" min={0} max={365} value={a} onChange={(e) => setA(Number(e.target.value))} /> días
      </label>
      <button className={stitchButton} disabled={g === green && a === amber} onClick={() => onSave(kind, kind === 'fiel' ? a : g, a)}>
        Guardar
      </button>
    </div>
  );
}
