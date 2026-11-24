import { useEffect, useState, type FormEvent } from 'react';
import { api } from '../api';
import { Field, Modal } from '../components/ui';
import { stitchButton, stitchPrimary } from '../components/stitch';
import './v11.css';

type Rule = { kind: string; day?: number; month?: number; months?: number } | null;
type Definition = {
  id: string;
  label: string;
  official_name: string;
  short_name: string;
  group_name: string;
  cadence: string;
  regime_scope: string | null;
  due_rule: Rule;
  due_text: string | null;
  aliases: string[];
};
const GROUPS = ['IVA', 'ISR', 'Retenciones', 'Informativas', 'Anuales'];
const CADENCES: [string, string][] = [
  ['monthly', 'Mensual'],
  ['bimonthly', 'Bimestral'],
  ['quarterly', 'Trimestral'],
  ['annual', 'Anual'],
];
const KINDS: [string, string][] = [
  ['', 'Sin regla (sin fecha de vencimiento)'],
  ['day_next_month', 'Día N del mes siguiente al periodo'],
  ['last_day_next_month', 'Último día del mes siguiente al periodo'],
  ['months_after_year_end', 'Último día del mes N del ejercicio siguiente'],
  ['fixed_next_year', 'Fecha fija del ejercicio siguiente'],
];
const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

export function ruleText(rule: Rule) {
  if (!rule) return 'Sin regla';
  if (rule.kind === 'day_next_month') return `Día ${rule.day} del mes siguiente`;
  if (rule.kind === 'last_day_next_month') return 'Último día del mes siguiente';
  if (rule.kind === 'months_after_year_end') return `Fin de ${MONTHS[(rule.months || 1) - 1]} del ejercicio siguiente`;
  if (rule.kind === 'fixed_next_year') return `${rule.day} de ${MONTHS[(rule.month || 1) - 1]} del ejercicio siguiente`;
  return 'Sin regla';
}

/** Plan v1.1, Cambio 2: the CSF obligations catalog; an administrator corrects wording and due rules. */
export default function ObligationCatalog({ notify }: { notify: (s: string) => void }) {
  const [items, setItems] = useState<Definition[]>([]);
  const [canEdit, setCanEdit] = useState(false);
  const [editing, setEditing] = useState<Definition | 'new' | null>(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    api<{ items: Definition[]; can_edit: boolean }>('/fiscal-control/catalog/csf')
      .then((d) => {
        setItems(d.items);
        setCanEdit(d.can_edit);
      })
      .catch((e) => notify(e.message));
  }, [reload, notify]);
  return (
    <div className="v11-catalog">
      <div className="card-title">
        <div>
          <h3>Catálogo de obligaciones de la constancia</h3>
          <p className="muted">
            El nombre oficial es el de la CSF y se compara sin mayúsculas, acentos ni puntuación. Las reglas de
            vencimiento las confirma el despacho.
          </p>
        </div>
        {canEdit && (
          <button className={stitchPrimary} onClick={() => setEditing('new')}>
            Agregar obligación
          </button>
        )}
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Grupo</th>
              <th scope="col">Nombre oficial (CSF)</th>
              <th scope="col">Nombre corto</th>
              <th scope="col">Periodicidad</th>
              <th scope="col">Vencimiento</th>
              {canEdit && <th scope="col">Acción</th>}
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id}>
                <td>{d.group_name}</td>
                <td>{d.official_name}</td>
                <td>{d.short_name}</td>
                <td>{CADENCES.find(([k]) => k === d.cadence)?.[1] || d.cadence}</td>
                <td title={d.due_text || ''}>{ruleText(d.due_rule)}</td>
                {canEdit && (
                  <td>
                    <button className={stitchButton} onClick={() => setEditing(d)}>
                      Editar
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && (
        <CatalogForm
          definition={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setReload((n) => n + 1);
            notify('Catálogo actualizado');
          }}
        />
      )}
    </div>
  );
}

function CatalogForm({ definition, onClose, onSaved }: { definition: Definition | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    official_name: definition?.official_name || '',
    short_name: definition?.short_name || '',
    group_name: definition?.group_name || 'ISR',
    cadence: definition?.cadence || 'monthly',
    regime_scope: definition?.regime_scope || '',
    due_text: definition?.due_text || '',
    kind: definition?.due_rule?.kind || '',
    day: definition?.due_rule?.day || 17,
    month: definition?.due_rule?.month || 4,
    months: definition?.due_rule?.months || 3,
    aliases: (definition?.aliases || []).join('\n'),
  });
  const [error, setError] = useState('');
  const set = (k: string, v: string | number) => setForm((f) => ({ ...f, [k]: v }));
  async function fromText() {
    const r = await api<{ due_rule: Rule }>('/fiscal-control/catalog/parse-due', 'POST', { text: form.due_text });
    if (r.due_rule) setForm((f) => ({ ...f, kind: r.due_rule!.kind, day: r.due_rule!.day || f.day, month: r.due_rule!.month || f.month, months: r.due_rule!.months || f.months }));
    else setError('No se reconoció la regla en el texto; elígela a mano.');
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    const due_rule = form.kind
      ? {
          kind: form.kind,
          ...(form.kind === 'day_next_month' ? { day: Number(form.day) } : {}),
          ...(form.kind === 'fixed_next_year' ? { day: Number(form.day), month: Number(form.month) } : {}),
          ...(form.kind === 'months_after_year_end' ? { months: Number(form.months) } : {}),
        }
      : null;
    const body = {
      official_name: form.official_name.trim(),
      short_name: form.short_name.trim(),
      group_name: form.group_name,
      cadence: form.cadence,
      regime_scope: form.regime_scope,
      due_rule,
      due_text: form.due_text,
    };
    try {
      if (definition)
        await api('/fiscal-control/catalog/' + definition.id, 'PUT', {
          ...body,
          aliases: form.aliases.split('\n').map((a) => a.trim()).filter(Boolean),
        });
      else await api('/fiscal-control/catalog', 'POST', { label: body.short_name, ...body });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <Modal title={definition ? 'Editar obligación' : 'Agregar obligación de constancia'} onClose={onClose}>
      <form className="form-grid" onSubmit={submit}>
        <Field label="Nombre oficial (como aparece en la CSF)">
          <input required maxLength={300} value={form.official_name} onChange={(e) => set('official_name', e.target.value)} />
        </Field>
        <Field label="Nombre corto">
          <input required maxLength={60} value={form.short_name} onChange={(e) => set('short_name', e.target.value)} />
        </Field>
        <Field label="Grupo">
          <select value={form.group_name} onChange={(e) => set('group_name', e.target.value)}>
            {GROUPS.map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </Field>
        <Field label="Periodicidad">
          <select value={form.cadence} onChange={(e) => set('cadence', e.target.value)}>
            {CADENCES.map(([k, l]) => (
              <option key={k} value={k}>
                {l}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Régimen o sujeto">
          <input maxLength={80} value={form.regime_scope} onChange={(e) => set('regime_scope', e.target.value)} />
        </Field>
        <Field label="Descripción del vencimiento (texto de la CSF)">
          <input maxLength={300} value={form.due_text} onChange={(e) => set('due_text', e.target.value)} />
        </Field>
        <div className="actions wide">
          <button type="button" className={stitchButton} disabled={!form.due_text} onClick={() => fromText().catch((e) => setError(e.message))}>
            Calcular regla desde el texto
          </button>
        </div>
        <Field label="Regla de vencimiento">
          <select value={form.kind} onChange={(e) => set('kind', e.target.value)}>
            {KINDS.map(([k, l]) => (
              <option key={k} value={k}>
                {l}
              </option>
            ))}
          </select>
        </Field>
        {(form.kind === 'day_next_month' || form.kind === 'fixed_next_year') && (
          <Field label="Día">
            <input type="number" min={1} max={31} value={form.day} onChange={(e) => set('day', e.target.value)} />
          </Field>
        )}
        {form.kind === 'fixed_next_year' && (
          <Field label="Mes">
            <select value={form.month} onChange={(e) => set('month', e.target.value)}>
              {MONTHS.map((m, i) => (
                <option key={m} value={i + 1}>
                  {m}
                </option>
              ))}
            </select>
          </Field>
        )}
        {form.kind === 'months_after_year_end' && (
          <Field label="Mes del ejercicio siguiente">
            <input type="number" min={1} max={12} value={form.months} onChange={(e) => set('months', e.target.value)} />
          </Field>
        )}
        {definition && (
          <Field label="Otras grafías que deben coincidir (una por línea)">
            <textarea rows={3} value={form.aliases} onChange={(e) => set('aliases', e.target.value)} />
          </Field>
        )}
        {error && (
          <p role="alert" className="error-banner wide">
            {error}
          </p>
        )}
        <div className="actions wide">
          <button type="button" className={stitchButton} onClick={onClose}>
            Cancelar
          </button>
          <button className={stitchPrimary}>Guardar</button>
        </div>
      </form>
    </Modal>
  );
}
