import { useState } from 'react';
import { api, authHeaders } from '../api';
import { Field, Kpi } from '../components/ui';
import { stitchButton, stitchCard, stitchPrimary } from '../components/stitch';
import type { State } from '../types';

type CellValue = {
  original?: unknown;
  status?: string;
  kind?: string;
  payment?: string;
  submitted_at?: string;
  requires_review?: boolean;
  requires_confirmation?: boolean;
  propose_company_not_applicable?: boolean;
  responsible_name?: string;
  interpreted?: string;
  matches_company_regime?: boolean;
  warnings?: string[];
};
type Cell = {
  header: string;
  role: string;
  obligation?: string;
  period?: string;
  value: CellValue;
  conflicts: string[];
};
type Row = {
  row_number: number;
  excel_name: string;
  period: string | null;
  company_id: string | null;
  company_match: string;
  conflicts: string[];
  cells: Cell[];
};
type SheetPreview = {
  name: string;
  period: string | null;
  rows: number;
  confirmed: number;
  proposed: number;
  ambiguous: number;
  unmatched: number;
  conflicts: number;
  truncated: boolean;
  detail: Row[];
};
type NameToConfirm = {
  excel_name: string;
  status: string;
  candidates: { id: string; name: string; rfc: string }[];
  sheets: string[];
};
type Result = {
  applied: boolean;
  sheets: SheetPreview[];
  ignored_sheets: { name: string; reason: string }[];
  unknown_columns: { header: string; reason: string; sheets: string[] }[];
  names_to_confirm: NameToConfirm[];
  catalog_available: boolean;
  equivalences_available: boolean;
  formula_cells_omitted: number;
};

const STATUS: Record<string, string> = {
  fulfilled: 'Cumplida',
  pending: 'Pendiente',
  not_applicable: 'No aplica',
  unreviewed: 'Sin revisar',
  in_progress: 'En proceso',
};
const PAYMENT: Record<string, string> = {
  paid: 'Pagado',
  pending: 'Pago pendiente',
  not_applicable: 'Sin pago',
  unknown: 'Pago desconocido',
};
const CONFLICT: Record<string, string> = {
  duplicate_cell: 'Celda duplicada',
  unknown_header: 'Encabezado desconocido',
  blank_header: 'Columna sin encabezado',
  not_added: 'Columna no incorporada',
  obligation_not_in_catalog: 'Obligación no existe en el catálogo',
  period_ambiguous: 'Periodo ambiguo',
  company_not_confirmed: 'Equivalencia sin confirmar',
  company_not_unique: 'Nombre ambiguo',
};
const MATCH: Record<string, string> = {
  rfc: 'Confirmada',
  confirmed: 'Confirmada',
  proposed: 'Propuesta por nombre',
  ambiguous: 'Ambigua',
  none: 'Sin equivalencia',
};

function original(value: unknown) {
  return value === null || value === undefined || value === '' ? '(vacío)' : String(value);
}

/** «Importar › Vista previa» of the Excel «Control de obligaciones»: nothing is written to the compliance matrix. */
export default function FiscalExcelPreview({ state, onBack }: { state: State; onBack: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [authorized, setAuthorized] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [data, setData] = useState<Result | null>(null);
  const [open, setOpen] = useState('');
  const [pick, setPick] = useState<Record<string, string>>({});

  async function analyze() {
    if (!file || !authorized) return;
    if (file.size > 15 * 1024 * 1024 || !file.name.toLowerCase().endsWith('.xlsx')) {
      setError('Se admite un XLSX de hasta 15 MB.');
      return;
    }
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const r = await fetch('/api/fiscal-control/import/preview?authorized_read=true', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { ...authHeaders(), 'Content-Type': 'application/octet-stream' },
        body: file,
      });
      if (!r.ok) {
        let msg = 'No fue posible analizar el archivo.';
        try {
          const e = await r.json();
          if (typeof e.detail === 'string') msg = e.detail;
        } catch {
          /* no raw server body */
        }
        throw new Error(msg);
      }
      setData(await r.json());
      setOpen('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function confirmName(name: string, company: string) {
    if (!company) return;
    setBusy(true);
    setError('');
    try {
      await api('/fiscal-control/import/equivalences', 'PUT', { excel_name: name, company_id: company });
      setMessage('Equivalencia confirmada. Vuelve a analizar el archivo para ver sus propuestas.');
      setData(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const sheet = data?.sheets.find((s) => s.name === open);
  return (
    <section className={stitchCard + ' padded stitch-live-module company-importer'} aria-busy={busy}>
      <button className={stitchButton} onClick={onBack}>
        Volver a fuentes
      </button>
      <h2>Control de obligaciones · vista previa</h2>
      <p>
        Lee el Excel en memoria y propone cómo quedaría cada celda. <strong>No se escribe ningún registro</strong>: el
        archivo no se conserva y el valor original de cada celda se muestra tal cual. Las hojas ocultas se ignoran.
      </p>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <Field label="Archivo XLSX">
        <input
          disabled={busy}
          type="file"
          accept=".xlsx"
          onChange={(e) => {
            setFile(e.target.files?.[0] || null);
            setAuthorized(false);
          }}
        />
      </Field>
      <label className="check-row">
        <input
          type="checkbox"
          disabled={busy || !file}
          checked={authorized}
          onChange={(e) => setAuthorized(e.target.checked)}
        />
        Autorizo el análisis de este archivo; no se aplicarán cambios definitivos.
      </label>
      <div className="actions">
        <button className={stitchPrimary} disabled={busy || !file || !authorized} onClick={() => void analyze()}>
          {busy ? 'Analizando…' : 'Analizar archivo'}
        </button>
      </div>
      {data && (
        <>
          <div className="kpi-grid four">
            <Kpi label="Hojas leídas" value={data.sheets.length} detail="Sólo hojas visibles" />
            <Kpi label="Hojas ignoradas" value={data.ignored_sheets.length} detail="Ocultas o vacías" />
            <Kpi
              label="Nombres por confirmar"
              value={data.names_to_confirm.length}
              detail="Sin equivalencia confirmada"
              tone={data.names_to_confirm.length ? 'amber' : undefined}
            />
            <Kpi label="Columnas no reconocidas" value={data.unknown_columns.length} detail="No se importan" />
          </div>
          {!data.catalog_available && (
            <p className="muted">El catálogo de obligaciones aún no está disponible: las columnas no se asocian.</p>
          )}
          {data.formula_cells_omitted > 0 && (
            <p className="muted">{data.formula_cells_omitted} celdas con fórmula se omitieron: nunca se evalúan.</p>
          )}
          <h3>Hojas</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Hoja</th>
                  <th>Periodo</th>
                  <th>Empresas</th>
                  <th>Confirmadas</th>
                  <th>Propuestas</th>
                  <th>Sin equivalencia</th>
                  <th>Conflictos</th>
                  <th>Detalle</th>
                </tr>
              </thead>
              <tbody>
                {data.sheets.map((s) => (
                  <tr key={s.name}>
                    <td>{s.name}</td>
                    <td>{s.period || 'Ambiguo'}</td>
                    <td>{s.rows}</td>
                    <td>{s.confirmed}</td>
                    <td>{s.proposed + s.ambiguous}</td>
                    <td>{s.unmatched}</td>
                    <td>{s.conflicts}</td>
                    <td>
                      <button
                        className={stitchButton}
                        aria-expanded={open === s.name}
                        onClick={() => setOpen(open === s.name ? '' : s.name)}
                      >
                        {open === s.name ? 'Ocultar' : 'Ver'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {sheet && (
            <div className="fiscal-excel-detail">
              <h3>Hoja {sheet.name}</h3>
              {sheet.truncated && <p className="muted">Se muestran las primeras filas de la hoja.</p>}
              {sheet.detail.map((row) => (
                <details key={row.row_number}>
                  <summary>
                    Fila {row.row_number} · {row.excel_name} · {MATCH[row.company_match] || row.company_match}
                    {row.conflicts.filter((c) => c !== 'company_not_confirmed').length > 0 &&
                      ' · ' +
                        row.conflicts
                          .filter((c) => c !== 'company_not_confirmed')
                          .map((c) => CONFLICT[c] || c)
                          .join(', ')}
                  </summary>
                  {row.cells.length === 0 ? (
                    <p className="muted">Sin equivalencia confirmada: la fila no entra a la propuesta.</p>
                  ) : (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Columna</th>
                            <th>Valor original</th>
                            <th>Propuesta</th>
                            <th>Avisos</th>
                          </tr>
                        </thead>
                        <tbody>
                          {row.cells.map((c, i) => (
                            <tr key={c.header + i}>
                              <td>
                                {c.header}
                                {c.period && <small> · periodo {c.period}</small>}
                              </td>
                              <td>{original(c.value.original)}</td>
                              <td>
                                {c.value.status ? STATUS[c.value.status] || c.value.status : '—'}
                                {c.value.submitted_at && <small> · presentada {c.value.submitted_at}</small>}
                                {c.value.payment && <small> · {PAYMENT[c.value.payment] || c.value.payment}</small>}
                                {c.value.responsible_name && (
                                  <small> · responsable propuesto: {c.value.responsible_name}</small>
                                )}
                                {c.value.interpreted && (
                                  <small>
                                    {' '}
                                    · régimen {c.value.interpreted}
                                    {c.value.matches_company_regime === false && ' (distinto al de la empresa)'}
                                  </small>
                                )}
                                {c.value.propose_company_not_applicable && (
                                  <small> · propone no aplicabilidad (requiere confirmación)</small>
                                )}
                              </td>
                              <td>
                                {[
                                  ...(c.value.warnings || []),
                                  ...(c.value.requires_review ? ['requiere revisión'] : []),
                                  ...c.conflicts.map((k) => CONFLICT[k] || k),
                                ].join(' · ') || '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </details>
              ))}
            </div>
          )}
          {data.unknown_columns.length > 0 && (
            <>
              <h3>Columnas no importadas</h3>
              <ul>
                {data.unknown_columns.map((u) => (
                  <li key={u.header}>
                    {u.header} · {CONFLICT[u.reason] || u.reason} · {u.sheets.length} hojas
                  </li>
                ))}
              </ul>
            </>
          )}
          {data.ignored_sheets.length > 0 && (
            <p className="muted">
              Hojas ignoradas:{' '}
              {data.ignored_sheets
                .map((s) => s.name + ' (' + (s.reason === 'hidden' ? 'oculta' : 'vacía') + ')')
                .join(', ')}
            </p>
          )}
          {data.names_to_confirm.length > 0 && (
            <>
              <h3>Nombres por confirmar</h3>
              <p className="muted">
                El Excel no trae RFC: una coincidencia de nombre sólo es una propuesta. Confirma a qué empresa
                corresponde cada nombre; la confirmación queda con tu usuario y fecha y se puede revocar.
              </p>
              {!data.equivalences_available && (
                <p className="muted">
                  Las equivalencias requieren una migración autorizada que aún no se aplicó: por ahora no se pueden
                  confirmar.
                </p>
              )}
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Nombre en el Excel</th>
                      <th>Estado</th>
                      <th>Empresa</th>
                      <th>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.names_to_confirm.map((n) => (
                      <tr key={n.excel_name}>
                        <td>{n.excel_name}</td>
                        <td>{MATCH[n.status] || 'Sin equivalencia'}</td>
                        <td>
                          <select
                            aria-label={'Empresa para ' + n.excel_name}
                            value={pick[n.excel_name] ?? (n.candidates.length === 1 ? n.candidates[0].id : '')}
                            onChange={(e) => setPick({ ...pick, [n.excel_name]: e.target.value })}
                          >
                            <option value="">Elegir empresa…</option>
                            {state.companies.map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.name} · {c.rfc}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <button
                            className={stitchButton}
                            disabled={
                              busy ||
                              !data.equivalences_available ||
                              !(pick[n.excel_name] ?? (n.candidates.length === 1 ? n.candidates[0].id : ''))
                            }
                            onClick={() =>
                              void confirmName(n.excel_name, pick[n.excel_name] ?? n.candidates[0]?.id ?? '')
                            }
                          >
                            Confirmar equivalencia
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
