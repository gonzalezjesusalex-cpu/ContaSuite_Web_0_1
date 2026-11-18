import { useMemo, useState } from 'react';
import { dateLabel } from '../api';
import type { Job, TaxRow } from '../types';

const MONTHS = [
  'Enero',
  'Febrero',
  'Marzo',
  'Abril',
  'Mayo',
  'Junio',
  'Julio',
  'Agosto',
  'Septiembre',
  'Octubre',
  'Noviembre',
  'Diciembre',
];
const SCOPES: Record<string, string> = { federal: 'Federales (ISR e IVA)', estatal: 'Estatales (ISN)', anual: 'Anuales' };
const QUALIFIERS: Record<string, string> = { COMPL: 'Complementaria', RESICO: 'RESICO', SALARIOS: 'Salarios' };
const REASONS: Record<string, string> = {
  acuse_sin_declaracion: 'Hay acuse, pero no hay una declaración con el mismo periodo y calificativo.',
  declaracion_sin_acuse: 'Hay declaración, pero falta su acuse.',
  acuse_adicional: 'Hay más acuses que declaraciones en este periodo.',
  sin_periodo: 'No se pudo determinar el periodo.',
};
const base = (p: string) => p.split('/').pop() || p;

type Entry = { key: string; decl?: TaxRow; acuse?: TaxRow; other?: TaxRow };
type Block = { key: string; scope: string; year: number; period: number; label: string; entries: Entry[] };

function periodLabel(r: TaxRow) {
  if (r.a === 'estatal') return `${r.n ?? '?'}.º bimestre`;
  if (r.a === 'anual') return 'Declaración anual';
  return r.n ? MONTHS[r.n - 1] : 'Sin periodo';
}

/** Declaraciones y acuses paired by period, folder and qualifiers; shows what is missing. Moves nothing. */
export default function TaxInventory({ job }: { job?: Job }) {
  const tax = job?.result.impuestos;
  const [scope, setScope] = useState('');
  const [state, setState] = useState('');
  const rows = useMemo(() => tax?.rows ?? [], [tax]);
  const blocks = useMemo(() => {
    const byPath = new Map(rows.map((r) => [r.p, r]));
    const map = new Map<string, Block>();
    const place = (r: TaxRow, entry: Entry) => {
      const q = r.q.map((k) => QUALIFIERS[k] || k).join(' · ');
      const key = [r.a, r.y ?? 0, r.n ?? 0, q].join('|');
      const block = map.get(key) ?? {
        key,
        scope: r.a,
        year: r.y ?? 0,
        period: r.n ?? 0,
        label: periodLabel(r) + (r.y ? ' ' + r.y : '') + (q ? ' · ' + q : ''),
        entries: [],
      };
      block.entries.push(entry);
      map.set(key, block);
    };
    for (const r of rows) {
      if (r.d === 'declaracion') place(r, { key: r.p, decl: r, acuse: r.pair ? byPath.get(r.pair) : undefined });
      else if (r.d === 'acuse' && !r.pair) place(r, { key: r.p, acuse: r });
      else if (r.d === 'otro') place(r, { key: r.p, other: r });
    }
    return [...map.values()].sort((a, b) => b.year - a.year || a.scope.localeCompare(b.scope) || a.period - b.period);
  }, [rows]);
  if (!job || !tax)
    return <p className="muted">Aún no hay inventario. Usa «Analizar carpeta» para que tu agente lo genere.</p>;
  const issue = (e: Entry) => [e.decl, e.acuse, e.other].some((r) => r && r.s !== 'ok');
  const visible = blocks
    .filter((b) => !scope || b.scope === scope)
    .map((b) => ({
      ...b,
      entries: b.entries.filter(
        (e) =>
          !state ||
          (state === 'faltante' && [e.decl, e.acuse].some((r) => r?.s === 'faltante')) ||
          (state === 'revisar' && [e.decl, e.acuse, e.other].some((r) => r?.s === 'revisar')) ||
          (state === 'ok' && !issue(e)),
      ),
    }))
    .filter((b) => b.entries.length);
  return (
    <div className="tax-inventory">
      <p>
        <strong>Declaraciones y acuses</strong> · {tax.total} archivos · {tax.pairs} pares · {tax.faltantes} con faltante ·{' '}
        {tax.revisar} por revisar · análisis del {dateLabel(job.created_at)}
      </p>
      <p className="muted">
        El emparejamiento usa el nombre y la carpeta de cada archivo (periodo, complementaria, RESICO, salarios). No
        acredita cumplimiento fiscal ni mueve archivos.
      </p>
      <div className="toolbar" style={{ flexWrap: 'wrap' }}>
        <select aria-label="Ámbito" value={scope} onChange={(e) => setScope(e.target.value)}>
          <option value="">Todos los ámbitos</option>
          {Object.entries(SCOPES).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select aria-label="Estado" value={state} onChange={(e) => setState(e.target.value)}>
          <option value="">Todos los estados</option>
          <option value="ok">Completos</option>
          <option value="faltante">Con faltante</option>
          <option value="revisar">Por revisar</option>
        </select>
      </div>
      {visible.map((b) => (
        <section className="tax-block" key={b.key}>
          <h4>
            {b.label} <small>{SCOPES[b.scope]}</small>
          </h4>
          {b.entries.map((e) => (
            <div className="tax-entry" key={e.key}>
              <div className="tax-docs">
                {e.decl && (
                  <span title={e.decl.p}>
                    <small>Declaración</small>
                    {base(e.decl.p)}
                  </span>
                )}
                {e.acuse && (
                  <span title={e.acuse.p}>
                    <small>Acuse{e.acuse.inf ? ' (inferido por el nombre)' : ''}</small>
                    {base(e.acuse.p)}
                  </span>
                )}
                {e.other && (
                  <span title={e.other.p}>
                    <small>Documento</small>
                    {base(e.other.p)}
                  </span>
                )}
              </div>
              {[e.decl, e.acuse, e.other]
                .filter((r): r is TaxRow => !!r && r.s !== 'ok')
                .map((r) => (
                  <small key={r.p} className={r.s === 'revisar' ? 'tax-why revisar' : 'tax-why'}>
                    {REASONS[r.why] || r.why}
                  </small>
                ))}
            </div>
          ))}
        </section>
      ))}
      {!visible.length && <p className="muted">Sin documentos con estos filtros.</p>}
    </div>
  );
}
