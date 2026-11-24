import { useEffect, useRef, useState, type FormEvent } from 'react';
import { UploadCloud } from 'lucide-react';
import { api } from '../api';
import { Badge, Field, Modal } from '../components/ui';
import { stitchButton, stitchCard, stitchPrimary } from '../components/stitch';
import DocumentLights, { describe, type CompanyLights } from './DocumentLights';
import './v11.css';

type Reading = {
  kind: 'sat_opinion' | 'imss_opinion' | 'infonavit' | 'csf';
  authority: string;
  fields: {
    rfc?: string | null;
    folio?: string | null;
    issued_on?: string | null;
    result?: string | null;
    workers?: number | null;
    bimester?: string | null;
    official_valid_until?: string | null;
    omissions?: { name: string; year: number; obligation_id?: string | null }[];
  };
  read: string[];
  warnings: string[];
  review: boolean;
  duplicate?: boolean;
  rfc_mismatch?: boolean;
  propose_not_applicable?: boolean;
};
const KIND_LABEL: Record<Reading['kind'], string> = {
  sat_opinion: 'Opinión de cumplimiento SAT (32-D)',
  imss_opinion: 'Opinión de cumplimiento IMSS',
  infonavit: 'Constancia de situación fiscal del Infonavit',
  csf: 'Constancia de Situación Fiscal (SAT)',
};

/** Plan v1.1, Cambio 1: the company's traffic light, with document capture read from the PDF and confirmed. */
export default function CompanyDocumentStatus({
  companyId,
  canUpload,
  canEdit,
  notify,
}: {
  companyId: string;
  canUpload: boolean;
  canEdit: boolean;
  notify: (s: string) => void;
}) {
  const [data, setData] = useState<CompanyLights | null>(null);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [reading, setReading] = useState<{ result: Reading; file: File } | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    api<{ companies: CompanyLights[] }>('/integral/document-status?company_id=' + companyId)
      .then((d) => setData(d.companies[0] || null))
      .catch((e) => setError(e.message));
  }, [companyId, reload]);
  async function analyze(file: File) {
    setBusy(true);
    try {
      const body = new FormData();
      body.append('file', file);
      const result = await api<Reading>(`/integral/companies/${companyId}/compliance/analyze`, 'POST', body);
      setReading({ result, file });
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  }
  async function notApplicable(kind: 'imss' | 'infonavit', value: boolean) {
    try {
      await api(`/integral/companies/${companyId}/document-settings`, 'PUT', { kind, not_applicable: value });
      setReload((n) => n + 1);
    } catch (e) {
      notify((e as Error).message);
    }
  }
  return (
    <section className={stitchCard + ' padded v11-document-status'}>
      <div className="card-title">
        <div>
          <h2>Semáforo documental</h2>
          <p>
            Vigencia según el despacho. Las lecturas se toman del documento; no hay consulta ni validación ante SAT, IMSS
            o Infonavit.
          </p>
        </div>
        {canUpload && (
          <div className="actions">
            <input
              ref={input}
              type="file"
              accept="application/pdf"
              hidden
              onChange={(e) => e.target.files?.[0] && analyze(e.target.files[0])}
            />
            <button className={stitchPrimary} disabled={busy} onClick={() => input.current?.click()}>
              <UploadCloud size={16} aria-hidden /> {busy ? 'Leyendo…' : 'Subir opinión o constancia'}
            </button>
          </div>
        )}
      </div>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {data && (
        <>
          <DocumentLights company={data} />
          <ul className="v11-light-details">
            {data.lights.map((l) => (
              <li key={l.kind}>
                {describe(l)}
                {canEdit && (l.kind === 'imss' || l.kind === 'infonavit') && (
                  <>
                    {' '}
                    {l.state === 'na' ? (
                      <button className={stitchButton} onClick={() => notApplicable(l.kind as 'imss', false)}>
                        Sí aplica
                      </button>
                    ) : (
                      <button className={stitchButton} onClick={() => notApplicable(l.kind as 'imss', true)}>
                        {l.propose_not_applicable ? 'Marcar «No aplica» (0 trabajadores)' : 'Marcar «No aplica»'}
                      </button>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {reading && (
        <ConfirmReading
          companyId={companyId}
          reading={reading.result}
          file={reading.file}
          onClose={() => setReading(null)}
          onSaved={() => {
            setReading(null);
            setReload((n) => n + 1);
            notify('Documento registrado y guardado en el expediente');
          }}
        />
      )}
    </section>
  );
}

function ConfirmReading({
  companyId,
  reading,
  file,
  onClose,
  onSaved,
}: {
  companyId: string;
  reading: Reading;
  file: File;
  onClose: () => void;
  onSaved: () => void;
}) {
  const f = reading.fields;
  const [form, setForm] = useState({
    rfc: f.rfc || '',
    folio: f.folio || '',
    issued_on: (f.issued_on || '').slice(0, 10),
    result: f.result || '',
    workers: f.workers == null ? '' : String(f.workers),
    official_valid_until: (f.official_valid_until || '').slice(0, 10),
    notes: '',
  });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const blocked = !!reading.rfc_mismatch || !!reading.duplicate;
  const tag = (key: string) =>
    reading.read.includes(key) ? (
      <Badge tone="blue">Leído del documento</Badge>
    ) : (
      <Badge>Captura manual</Badge>
    );
  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError('');
    const payload = {
      kind: reading.kind,
      rfc: form.rfc || null,
      folio: form.folio || null,
      issued_on: form.issued_on,
      result: reading.kind === 'csf' ? 'positive' : form.result,
      workers: form.workers === '' ? null : Number(form.workers),
      official_valid_until: form.official_valid_until || null,
      omissions: f.omissions || [],
      read: reading.read,
      notes: form.notes,
    };
    const body = new FormData();
    body.append('file', file);
    body.append('payload', JSON.stringify(payload));
    try {
      await api(`/integral/companies/${companyId}/compliance`, 'POST', body);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }
  const set = (k: string, v: string) => setForm((old) => ({ ...old, [k]: v }));
  return (
    <Modal title={KIND_LABEL[reading.kind]} onClose={onClose}>
      <form className="form-grid" onSubmit={submit}>
        {reading.warnings.length > 0 && (
          <div className="info-box wide" role="status">
            <ul>
              {reading.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        )}
        <Field label="RFC">
          <input value={form.rfc} readOnly aria-describedby="v11-rfc-tag" />
          <span id="v11-rfc-tag">{tag('rfc')}</span>
        </Field>
        {reading.kind !== 'csf' && (
          <Field label="Folio">
            <input value={form.folio} onChange={(e) => set('folio', e.target.value)} maxLength={60} />
            {tag('folio')}
          </Field>
        )}
        <Field label={reading.kind === 'infonavit' ? 'Fecha de expedición' : 'Fecha de emisión'}>
          <input type="date" required value={form.issued_on} onChange={(e) => set('issued_on', e.target.value)} />
          {tag('issued_on')}
        </Field>
        {reading.kind !== 'csf' && (
          <Field label="Resultado">
            <select required value={form.result} onChange={(e) => set('result', e.target.value)}>
              <option value="">Elige el resultado</option>
              <option value="positive">{reading.kind === 'infonavit' ? 'Sin adeudo' : 'Positiva'}</option>
              <option value="negative">{reading.kind === 'infonavit' ? 'Con adeudo' : 'Negativa'}</option>
              {reading.kind === 'imss_opinion' && <option value="no_opinion">Sin opinión</option>}
            </select>
            {tag('result')}
          </Field>
        )}
        {(reading.kind === 'imss_opinion' || reading.kind === 'infonavit') && (
          <Field label={'Trabajadores activos' + (f.bimester ? ' (' + f.bimester + ')' : '')}>
            <input type="number" min={0} value={form.workers} onChange={(e) => set('workers', e.target.value)} />
            {tag('workers')}
          </Field>
        )}
        {reading.kind !== 'csf' && reading.kind !== 'sat_opinion' && (
          <Field label="Vigencia oficial (como viene en el documento)">
            <input
              type="date"
              value={form.official_valid_until}
              onChange={(e) => set('official_valid_until', e.target.value)}
            />
          </Field>
        )}
        {(f.omissions?.length || 0) > 0 && (
          <div className="wide">
            <strong>Obligaciones omitidas</strong>
            <ul>
              {f.omissions!.map((o) => (
                <li key={o.name + o.year}>
                  {o.name} · {o.year}
                  {o.obligation_id ? ' · ligada al catálogo' : ' · sin coincidencia en el catálogo'}
                </li>
              ))}
            </ul>
          </div>
        )}
        {reading.propose_not_applicable && (
          <p className="muted wide">
            El documento reporta 0 trabajadores: puedes marcar IMSS e Infonavit como «No aplica» en el semáforo.
          </p>
        )}
        <Field label="Notas">
          <textarea rows={2} maxLength={2000} value={form.notes} onChange={(e) => set('notes', e.target.value)} />
        </Field>
        {error && (
          <p role="alert" className="error-banner wide">
            {error}
          </p>
        )}
        <div className="actions wide">
          <button type="button" className={stitchButton} onClick={onClose}>
            Cancelar
          </button>
          <button className={stitchPrimary} disabled={saving || blocked}>
            {blocked ? 'Queda para revisión' : saving ? 'Guardando…' : 'Confirmar y guardar'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
