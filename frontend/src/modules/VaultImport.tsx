import { useMemo, useState } from 'react';
import { AlertTriangle, Check, FileSpreadsheet } from 'lucide-react';
import { api, authHeaders } from '../api';
import { Field, Modal } from '../components/ui';
import { stitchButton, stitchDanger, stitchPrimary } from '../components/stitch';
import { isLockedError, useVault } from './VaultGate';

/** Renovación del gestor, fase 4: «Importar» in three steps (Archivo → Columnas → Revisar cambios), the template
 *  and the export. The file stays in the browser and is sent again at each step; the server never stores it and
 *  the preview never shows a password (only «igual» or «distinta»). */
type Sheet = {
  name: string;
  header_row: number | null;
  headers: string[];
  rows: number;
  has_rfc: boolean;
  mapping: string[];
  template: string | null;
};
type ReadResult = { file_name: string; sheets: Sheet[]; sheet: string | null; destinations: Record<string, string> };
type Option = { id: string; label: string };
type Line = {
  id: string;
  row: number;
  column: string;
  destination_label: string;
  action: string;
  action_label: string;
  detail: string;
  masked: string;
  decision: null | { id: string; options: Option[]; chosen: string | null; count: number };
};
type Entry = {
  rfc: string;
  row: number;
  company_id: string | null;
  name: string;
  notices: string[];
  decision: null | { id: string; options: Option[]; chosen: string | null };
  lines: Line[];
  repeated_rows: number[];
};
type Preview = {
  sha256: string;
  counts: { new: number; change: number; unchanged: number; decisions: number; review: number };
  companies: Entry[];
  ignored_rows: number;
  notices: string[];
};

async function download(path: string, init: RequestInit, filename: string) {
  const response = await fetch('/api' + path, { credentials: 'same-origin', ...init });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'No se pudo descargar.');
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return response;
}

/** «Descargar plantilla de Excel»: the headers of the office format, empty. */
export function downloadTemplate(notify: (s: string) => void) {
  download('/credentials/import/template', { headers: authHeaders() }, 'plantilla_contrasenas_contasuite.xlsx')
    .then(() => notify('Plantilla descargada.'))
    .catch((e) => notify(e.message));
}

const STEPS = ['Archivo', 'Columnas', 'Revisar cambios'];

export function ImportDialog({
  onClose,
  onDone,
  notify,
}: {
  onClose: () => void;
  onDone: () => void;
  notify: (s: string) => void;
}) {
  const vault = useVault();
  const [step, setStep] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [info, setInfo] = useState<ReadResult | null>(null);
  const [sheet, setSheet] = useState('');
  const [mapping, setMapping] = useState<string[]>([]);
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const current = info?.sheets.find((s) => s.name === sheet);

  function fail(e: unknown) {
    if (isLockedError(e)) vault.locked();
    else setError((e as Error).message);
  }
  function body(extra: Record<string, string> = {}) {
    const form = new FormData();
    form.append('file', file!);
    form.append('sheet', sheet);
    form.append('mapping', JSON.stringify(mapping));
    Object.entries(extra).forEach(([k, v]) => form.append(k, v));
    return form;
  }
  async function readFile(chosen: File) {
    setFile(chosen);
    setBusy(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', chosen);
      const r = await api<ReadResult>('/credentials/import/read', 'POST', form);
      setInfo(r);
      const first = r.sheets.find((s) => s.name === r.sheet) || r.sheets[0];
      setSheet(first?.name || '');
      setMapping(first?.mapping || []);
      setStep(1);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function review(next: Record<string, string> = decisions) {
    setBusy(true);
    setError('');
    try {
      setPreview(await api<Preview>('/credentials/import/preview', 'POST', body({ decisions: JSON.stringify(next) })));
      setStep(2);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  function decide(id: string, value: string) {
    const next = { ...decisions, [id]: value };
    setDecisions(next);
    review(next);
  }
  async function applyAll() {
    if (!preview) return;
    setBusy(true);
    setError('');
    try {
      const r = await api<{ message: string }>(
        '/credentials/import/apply',
        'POST',
        body({ decisions: JSON.stringify(decisions), sha256: preview.sha256 }),
      );
      notify(r.message);
      onDone();
      onClose();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  const total = preview ? preview.counts.new + preview.counts.change : 0;
  const rfcColumns = mapping.filter((m) => m === 'rfc').length;
  const options = useMemo(() => Object.entries(info?.destinations || {}), [info]);

  return (
    <Modal title="Importar contraseñas desde Excel" onClose={onClose}>
      <ol className="v2-import-steps" aria-label="Pasos de la importación">
        {STEPS.map((s, i) => (
          <li key={s} className={i === step ? 'is-current' : i < step ? 'is-done' : ''} aria-current={i === step}>
            {i < step ? <Check size={14} aria-hidden /> : <span>{i + 1}</span>} {s}
          </li>
        ))}
      </ol>
      {step === 0 && (
        <div className="v2-import-file">
          <FileSpreadsheet size={28} aria-hidden />
          <p>
            Sube el Excel (.xlsx) o un .csv de hasta 5 MB. Cada fila se relaciona con su empresa por el RFC. Nada se
            guarda hasta que pulses «Aplicar», y el archivo no se queda en el servidor.
          </p>
          <label className={stitchPrimary}>
            {busy ? 'Leyendo…' : 'Elegir archivo'}
            <input
              type="file"
              accept=".xlsx,.csv"
              hidden
              onChange={(e) => e.target.files?.[0] && readFile(e.target.files[0])}
            />
          </label>
        </div>
      )}
      {step === 1 && info && current && (
        <>
          {info.sheets.length > 1 && (
            <Field label="Hoja">
              <select
                value={sheet}
                onChange={(e) => {
                  const s = info.sheets.find((x) => x.name === e.target.value)!;
                  setSheet(s.name);
                  setMapping(s.mapping);
                }}
              >
                {info.sheets.map((s) => (
                  <option key={s.name} value={s.name} disabled={!s.has_rfc}>
                    {s.name} {s.has_rfc ? `· ${s.rows} filas` : '· sin columna RFC'}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <p className="muted small">
            Encabezados en la fila {current.header_row}.{' '}
            {current.template
              ? `Se reconoció el formato de «${current.template}».`
              : 'Revisa a qué va cada columna; se recordará para la próxima vez.'}
          </p>
          <div className="table-wrap">
            <table className="v2-import-columns">
              <thead>
                <tr>
                  <th scope="col">Encabezado en el Excel</th>
                  <th scope="col">Destino en el gestor</th>
                </tr>
              </thead>
              <tbody>
                {current.headers.map((h, i) => (
                  <tr key={i}>
                    <td>{h || <span className="muted">(sin título)</span>}</td>
                    <td>
                      <select
                        aria-label={'Destino de ' + (h || 'la columna ' + (i + 1))}
                        value={mapping[i]}
                        onChange={(e) => setMapping((m) => m.map((v, j) => (j === i ? e.target.value : v)))}
                      >
                        {options.map(([id, label]) => (
                          <option key={id} value={id}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rfcColumns !== 1 && (
            <p role="alert" className="error-banner">
              Asigna exactamente una columna como RFC.
            </p>
          )}
          <div className="actions">
            <button className={stitchButton} onClick={() => setStep(0)}>
              Atrás
            </button>
            <button className={stitchPrimary} disabled={busy || rfcColumns !== 1} onClick={() => review()}>
              {busy ? 'Revisando…' : 'Revisar cambios'}
            </button>
          </div>
        </>
      )}
      {step === 2 && preview && (
        <>
          <div className="v2-import-counts" role="status">
            <span>
              <strong>{preview.counts.new}</strong> nuevas
            </span>
            <span>
              <strong>{preview.counts.change}</strong> cambian
            </span>
            <span>
              <strong>{preview.counts.unchanged}</strong> sin cambios o vacías
            </span>
            <span className={preview.counts.decisions ? 'is-pending' : ''}>
              <strong>{preview.counts.decisions}</strong> necesitan tu decisión
            </span>
          </div>
          {preview.notices.map((n) => (
            <p key={n} className="v2-import-notice">
              <AlertTriangle size={14} aria-hidden /> {n}
            </p>
          ))}
          <div className="v2-import-companies">
            {preview.companies.map((c) => (
              <section key={c.rfc} className="v2-import-company" aria-label={c.name + ' · ' + c.rfc}>
                <header>
                  <strong>{c.name}</strong>{' '}
                  <span className="muted">
                    · {c.rfc} · fila {c.row}
                  </span>
                  {!c.company_id && <span className="v2-import-tag">No existe en ContaSuite</span>}
                </header>
                {c.decision && (
                  <div className="v2-import-decision" role="group" aria-label={'Qué hacer con ' + c.rfc}>
                    {c.decision.options.map((o) => (
                      <label key={o.id} className="check-option">
                        <input
                          type="radio"
                          name={c.decision!.id}
                          checked={c.decision!.chosen === o.id}
                          onChange={() => decide(c.decision!.id, o.id)}
                        />{' '}
                        {o.label}
                      </label>
                    ))}
                  </div>
                )}
                {c.notices.map((n) => (
                  <p key={n} className="v2-import-notice">
                    <AlertTriangle size={14} aria-hidden /> {n}
                  </p>
                ))}
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Columna</th>
                      <th scope="col">Valor</th>
                      <th scope="col">Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.lines.map((l) => (
                      <tr key={l.id} className={'is-' + l.action}>
                        <td>{l.column}</td>
                        <td>
                          <span aria-label="Valor oculto">{l.masked}</span> <span className="muted">{l.detail}</span>
                        </td>
                        <td>
                          {l.decision ? (
                            <select
                              aria-label={'Valor de ' + l.column}
                              value={l.decision.chosen || ''}
                              onChange={(e) => decide(l.decision!.id, e.target.value)}
                            >
                              <option value="" disabled>
                                Elige cuál…
                              </option>
                              {l.decision.options.map((o) => (
                                <option key={o.id} value={o.id}>
                                  {o.label}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <strong>{l.action_label}</strong>
                          )}
                          {l.decision?.chosen && <span className="muted"> · {l.action_label}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            ))}
          </div>
          <div className="actions">
            <button className={stitchButton} onClick={() => setStep(1)}>
              Atrás
            </button>
            <button
              className={stitchPrimary}
              disabled={busy || !!preview.counts.decisions || total === 0}
              onClick={applyAll}
            >
              Aplicar {total} cambios
            </button>
          </div>
        </>
      )}
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
    </Modal>
  );
}

export function ExportDialog({
  companies,
  companyId,
  onClose,
  onLocked,
  notify,
}: {
  companies: { id: string }[];
  companyId?: string;
  onClose: () => void;
  onLocked: () => void;
  notify: (s: string) => void;
}) {
  const [reason, setReason] = useState('');
  const [password, setPassword] = useState('');
  const [onlyThis, setOnlyThis] = useState(!!companyId);
  async function run() {
    try {
      await download(
        '/credentials/export',
        {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            reason,
            password,
            company_ids: onlyThis && companyId ? [companyId] : companies.map((c) => c.id),
          }),
        },
        'contrasenas_contasuite.xlsx',
      );
      setPassword('');
      notify('Exportación lista. Protege el archivo y bórralo cuando termines.');
      onClose();
    } catch (e) {
      setPassword('');
      if (isLockedError(e)) onLocked();
      else notify((e as Error).message);
    }
  }
  return (
    <Modal title="Exportar contraseñas" onClose={onClose}>
      <p role="alert" className="error-banner">
        El archivo tendrá las contraseñas en claro, con el mismo formato que la plantilla. Guárdalo cifrado, no lo
        envíes por correo y bórralo al terminar. La exportación queda en la bitácora con tu motivo.
      </p>
      <Field label="Motivo">
        <input required minLength={3} maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <Field label="Tu contraseña maestra">
        <input
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      {companyId && (
        <label className="check-option">
          <input type="checkbox" checked={onlyThis} onChange={(e) => setOnlyThis(e.target.checked)} /> Sólo esta empresa
        </label>
      )}
      <div className="actions">
        <button className={stitchButton} onClick={onClose}>
          Cancelar
        </button>
        <button className={stitchDanger} disabled={reason.trim().length < 3 || !password} onClick={run}>
          Exportar
        </button>
      </div>
    </Modal>
  );
}
