import { markDirty } from '../dirtyForms';
import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Check, Save, FolderOpen, ShieldCheck } from 'lucide-react';
import { clearDirtyForms } from '../navigationGuard';
import { api } from '../api';
import { Field, Heading, Badge } from '../components/ui';
import type { Company, Responsible } from '../types';
import { PreviousAccessField, ResponsibleSelect, saveResponsible, type PreviousAccess } from './ResponsibleSelect';
import CsfCard, { type CsfRegime, type CsfResult } from './CsfCard';
const blank = {
  name: '',
  rfc: '',
  person_type: 'Moral' as const,
  trade_name: '',
  regime: '601 - General de Ley Personas Morales',
  accountant: 'Sin asignar',
  email: '',
  phone: '',
  location: '',
  folder: '',
  notes: '',
  // Bloque 1: data of the Constancia de Situación Fiscal.
  idcif: '',
  curp: '',
  tax_postal_code: '',
  tax_street_type: '',
  tax_street: '',
  tax_exterior_number: '',
  tax_interior_number: '',
  tax_neighborhood: '',
  tax_locality: '',
  tax_municipality: '',
  tax_state: '',
  tax_between_streets: '',
  operations_start: '',
  padron_status: '',
  csf_issued_on: '',
};
type Form = Record<string, string> & { person_type: Company['person_type'] };
const DATES = ['operations_start', 'csf_issued_on'];
const ADDRESS: [string, string][] = [
  ['tax_postal_code', 'Código postal'],
  ['tax_street_type', 'Tipo de vialidad'],
  ['tax_street', 'Nombre de vialidad'],
  ['tax_exterior_number', 'Número exterior'],
  ['tax_interior_number', 'Número interior'],
  ['tax_neighborhood', 'Colonia'],
  ['tax_locality', 'Localidad'],
  ['tax_municipality', 'Municipio o demarcación'],
  ['tax_state', 'Entidad federativa'],
  ['tax_between_streets', 'Entre calles'],
];

export default function CompanyForm({
  company,
  onSaved,
  notify,
  userId,
  admin = false,
  responsible,
  ocrAvailable = false,
}: {
  company?: Company;
  userId?: string;
  /** Only an administrator assigns the responsible accountant (Bloque 2). */
  admin?: boolean;
  responsible?: Responsible | null;
  /** The server reports whether the local OCR is installed (Bloque 1). */
  ocrAvailable?: boolean;
  onSaved: () => Promise<void>;
  notify: (message: string) => void;
}) {
  const navigate = useNavigate();
  const [form, setForm] = useState<Form>(
    company
      ? (Object.fromEntries(
          Object.keys(blank).map((k) => [k, (company as unknown as Record<string, unknown>)[k] ?? '']),
        ) as Form)
      : (blank as unknown as Form),
  );
  const [step, setStep] = useState(0);
  const [regimes, setRegimes] = useState<{ code: string; label: string; fisica: boolean; moral: boolean }[]>([]);
  useEffect(() => {
    const abort = new AbortController();
    api<typeof regimes>('/sat/regimes', 'GET', undefined, abort.signal)
      .then(setRegimes)
      .catch(() => undefined); // the stored value stays selectable; saving still validates on the server
    return () => abort.abort();
  }, []);
  const [responsibleId, setResponsibleId] = useState(company?.accountant_id || '');
  const [previousAccess, setPreviousAccess] = useState<PreviousAccess | ''>('');
  // Constancia: which fields came from it, which were read with low confidence, its notices and regimes.
  const [csfMode, setCsfMode] = useState<'choose' | 'manual' | 'read'>(company ? 'manual' : 'choose');
  const [csf, setCsf] = useState<CsfResult | null>(null);
  const [csfFile, setCsfFile] = useState<File | null>(null);
  const [fromCsf, setFromCsf] = useState<Set<string>>(new Set());
  const [csfRegimes, setCsfRegimes] = useState<CsfRegime[] | null>(null);
  const shownRegimes = regimes.filter((r) => (form.person_type === 'Moral' ? r.moral : r.fisica));
  const responsibleChanged = admin && responsibleId !== (company?.accountant_id || '');
  const [busy, setBusy] = useState(false);
  const set = (key: string, value: string) => {
    setForm((v) => ({ ...v, [key]: value }));
    // An edited value is the user's, no longer the constancia's reading.
    setFromCsf((old) => {
      if (!old.has(key)) return old;
      const next = new Set(old);
      next.delete(key);
      return next;
    });
  };
  const draftKey = 'contasuite-company-draft:' + userId + ':' + (company?.id || 'new');
  const saveDraft = () => {
    localStorage.setItem(draftKey, JSON.stringify(form));
    notify('Borrador guardado en este navegador');
  };
  const loadDraft = () => {
    try {
      const d = JSON.parse(localStorage.getItem(draftKey) || 'null');
      if (d) {
        setForm({ ...(blank as unknown as Form), ...d });
        setCsfMode('manual');
        const form = document.querySelector<HTMLFormElement>('.registration-form');
        if (form) markDirty(form);
        notify('Borrador recuperado');
      } else notify('No hay borrador guardado');
    } catch {
      notify('El borrador no es válido');
    }
  };
  function applyCsf(result: CsfResult, file: File) {
    const values: Record<string, string> = {};
    for (const [key, value] of Object.entries(result.fields))
      if (key in blank && typeof value === 'string') values[key] = value;
    setForm((old) => ({ ...old, ...values }));
    setFromCsf(new Set(Object.keys(values)));
    setCsfRegimes(result.fields.regimes || null);
    setCsf(result);
    setCsfFile(file);
    setCsfMode('read');
    const el = document.querySelector<HTMLFormElement>('.registration-form');
    if (el) markDirty(el);
  }
  const low = new Set(csf?.low_confidence || []);
  // Label helper: marks values taken from the constancia, in amber when the reading needs review.
  const mark = (key: string, input: ReactNode) => (
    <>
      {input}
      {fromCsf.has(key) && (
        <span className="csf-origin">
          <Badge tone={low.has(key) ? 'amber' : 'blue'}>
            {low.has(key) ? 'De la constancia · revísalo' : 'De la constancia'}
          </Badge>
        </span>
      )}
    </>
  );
  const fieldClass = (key: string) => (fromCsf.has(key) && low.has(key) ? 'low-confidence' : undefined);
  function payload() {
    const data: Record<string, unknown> = { ...form };
    for (const key of DATES) data[key] = form[key] || null;
    if (csfRegimes) {
      // The chosen main regime goes first; regimes read from the constancia keep their dates.
      const main = csfRegimes.find((r) => r.label === form.regime);
      const rest = csfRegimes.filter((r) => r !== main);
      const code = regimes.find((r) => r.label === form.regime)?.code || null;
      data.regimes = [main || { code, label: form.regime, start_date: null, end_date: null }, ...rest];
    }
    return data;
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (step < 2) {
      setStep(step + 1);
      return;
    }
    setBusy(true);
    try {
      const c = await api<Company>(
        '/companies' + (company ? '/' + company.id : ''),
        company ? 'PUT' : 'POST',
        payload(),
      );
      if (responsibleChanged) {
        // The responsible is assigned by user through its own endpoint, never as free text.
        const notices = await saveResponsible(company || { ...c, accountant_id: null }, responsibleId, previousAccess);
        notices.forEach(notify);
      }
      if (csfFile) await attachCsf(c.id, csfFile, notify);
      await onSaved();
      if (!company) localStorage.removeItem(draftKey);
      notify(company ? 'Empresa actualizada' : 'Empresa registrada');
      clearDirtyForms();
      navigate('/empresas/' + c.id + location.search);
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const physical = form.person_type === 'Física';
  return (
    <>
      {company?.archived && (
        <p role="alert" className="error-banner">
          Empresa archivada: editar sus datos no la restaura.
        </p>
      )}
      <button className="back-link" onClick={() => navigate('/empresas')}>
        <ArrowLeft size={16} />
        Volver a Empresas
      </button>
      <Heading
        title={company ? 'Editar empresa' : 'Registrar empresa'}
        description="Alta del contribuyente, asignación contable y vinculación de expediente digital."
        actions={
          <>
            <button className="btn" onClick={loadDraft}>
              Recuperar borrador
            </button>
            <button className="btn" onClick={saveDraft}>
              <Save size={16} />
              Guardar borrador
            </button>
          </>
        }
      />
      <div className="registration-layout">
        <form onSubmit={submit} className="card registration-form">
          <div className="stepper">
            {['Datos generales', 'Información fiscal', 'Expediente digital'].map((t, i) => (
              <button
                key={t}
                type="button"
                className={i === step ? 'active' : ''}
                onClick={() => {
                  if (i < step) setStep(i);
                }}
              >
                <span>{i < step ? <Check size={14} /> : i + 1}</span>
                <div>
                  {t}
                  <small>{['Identidad y contacto fiscal', 'Régimen y domicilio', 'Carpeta del servidor'][i]}</small>
                </div>
              </button>
            ))}
          </div>
          <h2>
            Paso {step + 1}:{' '}
            {['Identidad del contribuyente', 'Régimen y domicilio fiscal', 'Expediente documental'][step]}
          </h2>
          <p className="muted">
            {
              [
                'Captura la información tal como aparece en la Constancia de Situación Fiscal, o léela del PDF.',
                'El régimen, el domicilio y las obligaciones deben revisarse contra la constancia del contribuyente.',
                'La ruta será utilizada por el agente instalado en el equipo Windows.',
              ][step]
            }
          </p>
          {csf && (csf.warnings.length > 0 || csf.existing_company) && (
            <div className="error-banner csf-warnings" role="alert">
              <ul>
                {csf.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
              {csf.existing_company?.id && (
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    clearDirtyForms();
                    navigate('/empresas/' + csf.existing_company!.id);
                  }}
                >
                  Abrir {csf.existing_company.name}
                </button>
              )}
            </div>
          )}
          <div className="form-grid">
            {step === 0 && !company && csfMode === 'choose' && (
              <CsfCard ocrAvailable={ocrAvailable} onResult={applyCsf} onManual={() => setCsfMode('manual')} />
            )}
            {step === 0 && csfMode === 'read' && csf && (
              <p className="csf-summary wide" role="status">
                Datos leídos de la constancia ({csf.source === 'ocr' ? 'escaneo, con OCR local' : 'PDF con texto'};
                {csf.pages.length === 1 ? ' página ' : ' páginas '}
                {csf.pages.join(', ')} de {csf.page_count}). Revisa cada campo antes de registrar; al guardar se
                adjuntan al expediente sólo esas páginas.
              </p>
            )}
            {step === 0 && csfMode !== 'choose' && (
              <>
                <Field label="Tipo de contribuyente *">
                  {mark(
                    'person_type',
                    <select value={form.person_type} onChange={(e) => set('person_type', e.target.value)}>
                      <option>Moral</option>
                      <option>Física</option>
                    </select>,
                  )}
                </Field>
                <Field label="RFC *">
                  {mark(
                    'rfc',
                    <input
                      required
                      className={fieldClass('rfc')}
                      value={form.rfc}
                      maxLength={30}
                      minLength={12}
                      placeholder="DBA180412KJ9"
                      onChange={(e) => set('rfc', e.target.value.replace(/\s/g, '').toUpperCase())}
                    />,
                  )}
                </Field>
                <Field label={company ? 'idCIF' : 'idCIF *'}>
                  {mark(
                    'idcif',
                    <input
                      required={!company}
                      className={fieldClass('idcif')}
                      inputMode="numeric"
                      pattern="\d{8,11}"
                      title="De 8 a 11 dígitos, tal como aparece en la constancia"
                      value={form.idcif}
                      onChange={(e) => set('idcif', e.target.value.replace(/\D/g, '').slice(0, 11))}
                    />,
                  )}
                </Field>
                <Field label={physical && !company ? 'CURP *' : 'CURP'}>
                  {mark(
                    'curp',
                    <input
                      required={physical && !company}
                      className={fieldClass('curp')}
                      maxLength={18}
                      minLength={18}
                      value={form.curp}
                      onChange={(e) => set('curp', e.target.value.replace(/\s/g, '').toUpperCase())}
                    />,
                  )}
                </Field>
                <Field label="Razón social / Nombre completo *" wide>
                  {mark(
                    'name',
                    <input
                      required
                      className={fieldClass('name')}
                      minLength={2}
                      maxLength={220}
                      value={form.name}
                      onChange={(e) => set('name', e.target.value)}
                    />,
                  )}
                </Field>
                <Field label="Nombre comercial">
                  {mark(
                    'trade_name',
                    <input value={form.trade_name} onChange={(e) => set('trade_name', e.target.value)} />,
                  )}
                </Field>
                <Field label="Contador responsable">
                  {admin ? (
                    <ResponsibleSelect
                      value={responsibleId}
                      current={responsible}
                      onChange={setResponsibleId}
                      disabled={busy}
                    />
                  ) : (
                    <input
                      readOnly
                      value={company?.accountant_id ? company.accountant : 'Sin asignar'}
                      aria-describedby="responsible-help"
                    />
                  )}
                  {!admin && <small id="responsible-help">Lo asigna la administración.</small>}
                </Field>
                {responsibleChanged && company?.accountant_id && (
                  <PreviousAccessField value={previousAccess} onChange={setPreviousAccess} disabled={busy} />
                )}
                <Field label="Correo electrónico">
                  <input type="email" value={form.email} onChange={(e) => set('email', e.target.value)} />
                </Field>
                <Field label="Teléfono">
                  <input value={form.phone} onChange={(e) => set('phone', e.target.value)} />
                </Field>
                <Field label="Ciudad / Estado" wide>
                  {mark('location', <input value={form.location} onChange={(e) => set('location', e.target.value)} />)}
                </Field>
              </>
            )}
            {step === 1 && (
              <>
                <Field label="Régimen fiscal principal *" wide>
                  {mark(
                    'regime',
                    <select required value={form.regime} onChange={(e) => set('regime', e.target.value)}>
                      {!form.regime && <option value="">Selecciona el régimen</option>}
                      {/* A stored value outside the catalog (older data) stays selectable until it is changed. */}
                      {form.regime && !shownRegimes.some((r) => r.label === form.regime) && (
                        <option value={form.regime}>{form.regime}</option>
                      )}
                      {shownRegimes.map((r) => (
                        <option key={r.code} value={r.label}>
                          {r.label}
                        </option>
                      ))}
                    </select>,
                  )}
                </Field>
                {csfRegimes && csfRegimes.length > 0 && (
                  <div className="info-box wide">
                    <div>
                      <strong>Regímenes vigentes en la constancia</strong>
                      <ul className="csf-regimes">
                        {csfRegimes.map((r) => (
                          <li key={r.label}>
                            {r.label}
                            {r.start_date && <small> · desde {r.start_date}</small>}
                          </li>
                        ))}
                      </ul>
                      {(csf?.unmatched_regimes.length || 0) > 0 && (
                        <p>
                          Sin coincidencia en el catálogo (elige el régimen manualmente):{' '}
                          {csf!.unmatched_regimes.join('; ')}
                        </p>
                      )}
                    </div>
                  </div>
                )}
                <Field label="Fecha de inicio de operaciones">
                  {mark(
                    'operations_start',
                    <input
                      type="date"
                      value={form.operations_start}
                      onChange={(e) => set('operations_start', e.target.value)}
                    />,
                  )}
                </Field>
                <Field label="Estatus en el padrón">
                  {mark(
                    'padron_status',
                    <input
                      className={form.padron_status && form.padron_status !== 'ACTIVO' ? 'low-confidence' : undefined}
                      value={form.padron_status}
                      onChange={(e) => set('padron_status', e.target.value.toUpperCase())}
                    />,
                  )}
                </Field>
                <Field label="Fecha de emisión de la constancia">
                  {mark(
                    'csf_issued_on',
                    <input
                      type="date"
                      value={form.csf_issued_on}
                      onChange={(e) => set('csf_issued_on', e.target.value)}
                    />,
                  )}
                </Field>
                <fieldset className="csf-address wide">
                  <legend>Domicilio fiscal</legend>
                  <div className="form-grid">
                    {ADDRESS.map(([key, label]) => (
                      <Field key={key} label={label} wide={key === 'tax_between_streets'}>
                        {mark(
                          key,
                          <input
                            className={fieldClass(key)}
                            value={form[key]}
                            inputMode={key === 'tax_postal_code' ? 'numeric' : undefined}
                            pattern={key === 'tax_postal_code' ? '\\d{5}' : undefined}
                            onChange={(e) => set(key, e.target.value)}
                          />,
                        )}
                      </Field>
                    ))}
                  </div>
                </fieldset>
                <div className="info-box wide">
                  <ShieldCheck size={20} />
                  <div>
                    <strong>Registro interno del despacho</strong>
                    <p>
                      El alta valida la estructura del RFC, de la CURP y del idCIF y evita duplicados. La lectura de la
                      constancia es local y no constituye validación ante el SAT; la consulta al SAT y las listas 69-B
                      no están integradas.
                    </p>
                  </div>
                </div>
                <Field label="Observaciones fiscales" wide>
                  {mark(
                    'notes',
                    <textarea rows={5} value={form.notes} onChange={(e) => set('notes', e.target.value)} />,
                  )}
                </Field>
              </>
            )}
            {step === 2 && (
              <>
                <Field label="Ruta de carpeta local o de red (opcional)" wide>
                  <input
                    value={form.folder}
                    placeholder="C:\Empresas\RFC o \\servidor\empresas\RFC"
                    onChange={(e) => set('folder', e.target.value)}
                  />
                </Field>
                <div className="upload-placeholder wide">
                  <FolderOpen size={32} />
                  <strong>Vincula la carpeta de la empresa</strong>
                  <p>
                    Después del alta podrás analizar su contenido desde el expediente. La ruta debe estar autorizada en
                    la configuración del agente.
                  </p>
                </div>
                <div className="info-box wide">
                  <p>
                    Los documentos PDF, XML y CER se adjuntan desde el expediente. Las llaves .key y sus contraseñas
                    permanecen en el equipo local.
                    {csfFile && ' La constancia leída se adjuntará al expediente (sólo sus páginas).'}
                  </p>
                </div>
              </>
            )}
          </div>
          <footer className="form-footer">
            <button type="button" className="btn" onClick={() => (step ? setStep(step - 1) : navigate('/empresas'))}>
              {step ? 'Anterior' : 'Cancelar'}
            </button>
            <button disabled={busy || (step === 0 && csfMode === 'choose')} className="btn primary" type="submit">
              {busy ? (
                'Guardando…'
              ) : step < 2 ? (
                'Siguiente →'
              ) : (
                <>
                  <Check size={16} />
                  {company ? 'Guardar cambios' : 'Guardar y dar de alta'}
                </>
              )}
            </button>
          </footer>
        </form>
        <aside className="card registration-summary">
          <h3>Resumen de alta</h3>
          <div className="company-avatar">{form.name.slice(0, 2).toUpperCase() || 'CS'}</div>
          <h2>{form.name || 'Nuevo contribuyente'}</h2>
          <p className="rfc">{form.rfc || 'RFC pendiente'}</p>
          <Badge>{form.person_type === 'Moral' ? 'Persona moral' : 'Persona física'}</Badge>
          <hr />
          <p className="eyebrow">PUNTOS DE CONTROL</p>
          {[
            [form.name.length > 1, 'Nombre del contribuyente'],
            [form.rfc.length === (form.person_type === 'Moral' ? 12 : 13), 'Estructura RFC capturada'],
            [/^\d{8,11}$/.test(form.idcif), 'idCIF capturado'],
            [!!(admin ? responsibleId : company?.accountant_id), 'Contador asignado'],
            [!!form.folder, 'Ruta del expediente'],
          ].map(([ok, text]) => (
            <div className="check-line" key={String(text)}>
              <span className={ok ? 'green-text' : 'muted'}>{ok ? '✓' : '○'}</span>
              {text}
            </div>
          ))}
          <small className="muted">La captura de datos no constituye validación oficial ante el SAT.</small>
        </aside>
      </div>
    </>
  );
}

/** After registering, attach only the pages of the constancia to the company file (Bloque 1). */
async function attachCsf(companyId: string, file: File, notify: (m: string) => void) {
  // The server locates the pages of the constancia again; the rest of the PDF is never stored.
  const body = new FormData();
  body.append('file', file);
  try {
    await api('/companies/' + companyId + '/csf/attach', 'POST', body);
  } catch (e) {
    // The company is already saved; the user can attach the constancia from the file later.
    notify('La empresa se guardó, pero no se adjuntó la constancia: ' + (e as Error).message);
  }
}
