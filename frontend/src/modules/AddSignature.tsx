import { useEffect, useRef, useState, type DragEvent } from 'react';
import { CheckCircle2, FileKey2, ShieldCheck, Upload, XCircle } from 'lucide-react';
import { api } from '../api';
import { Field, Modal } from '../components/ui';
import { stitchButton, stitchPrimary } from '../components/stitch';
import { isLockedError, useVault } from './VaultGate';

/** Renovación del gestor, fase 3: «Agregar FIEL o CSD». The .cer and the .key are checked together on the server
 *  (read certificate, password opens the key, key matches the certificate, class, RFC, validity) and «Guardar»
 *  is enabled only when every check passes. Nothing is stored until then; nothing is ever downloaded. */
export type SignatureClass = 'FIEL_EMPRESA' | 'FIEL_REPRESENTANTE' | 'CSD';
type Check = { id: string; ok: boolean; message: string; blocking: boolean; suggestion?: SignatureClass | null };
type Result = {
  read: null | {
    holder_name: string;
    rfc: string;
    representative_rfc: string;
    curp: string;
    number: string;
    issuer: string;
    branch: string;
    valid_from: string;
    valid_until: string;
    detected: 'FIEL' | 'CSD';
    days_left: number;
  };
  checks: Check[];
  sat_access?: { cer: string; key: string; password: string; rfc: string };
  replaces?: boolean;
  duplicate?: boolean;
};
const CLASSES: { id: SignatureClass; label: string; hint: string }[] = [
  { id: 'FIEL_EMPRESA', label: 'FIEL de la empresa', hint: 'e.firma con el RFC de la empresa' },
  { id: 'FIEL_REPRESENTANTE', label: 'FIEL del representante', hint: 'e.firma de la persona física que representa' },
  { id: 'CSD', label: 'Sello digital (CSD)', hint: 'Certificado de sello para facturar, por sucursal' },
];
const CHECK_LABELS: Record<string, string> = {
  certificate: 'Certificado del SAT',
  password: 'Contraseña de la clave privada',
  pair: 'La clave privada corresponde al .cer',
  class: 'Tipo de firma',
  rfc: 'RFC',
  validity: 'Vigencia',
};

export default function AddSignature({
  companies,
  companyId,
  initialClass = 'FIEL_EMPRESA',
  onClose,
  onSaved,
}: {
  companies: { id: string; name: string; rfc: string; can_create: boolean }[];
  companyId?: string;
  initialClass?: SignatureClass;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const vault = useVault();
  const allowed = companies.filter((c) => c.can_create);
  const [company, setCompany] = useState(companyId || allowed[0]?.id || '');
  const [klass, setKlass] = useState<SignatureClass>(initialClass);
  const [cer, setCer] = useState<File | null>(null);
  const [key, setKey] = useState<File | null>(null);
  const [password, setPassword] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [checking, setChecking] = useState(false);
  const [replace, setReplace] = useState(false);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const round = useRef(0);

  function take(list: FileList | null) {
    for (const file of Array.from(list || [])) {
      const ext = file.name.toLowerCase().split('.').pop();
      if (ext === 'cer') setCer(file);
      else if (ext === 'key') setKey(file);
      else setError(`«${file.name}» no es un .cer ni un .key.`);
    }
  }
  function form() {
    const body = new FormData();
    body.append('cer', cer!);
    body.append('key', key!);
    body.append('password', password);
    body.append('cert_class', klass);
    return body;
  }
  // The password is validated at once (debounced while typing).
  useEffect(() => {
    setResult(null);
    setReplace(false);
    if (!company || !cer || !key || !password) return;
    const mine = ++round.current;
    const t = window.setTimeout(async () => {
      setChecking(true);
      setError('');
      try {
        const r = await api<Result>(`/credentials/companies/${company}/certificates/check`, 'POST', form());
        if (mine === round.current) setResult(r);
      } catch (e) {
        if (isLockedError(e)) vault.locked();
        else if (mine === round.current) setError((e as Error).message);
      } finally {
        if (mine === round.current) setChecking(false);
      }
    }, 450);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [company, klass, cer, key, password]);

  const blocking = result?.checks.filter((c) => c.blocking && !c.ok) || [];
  const expired = result?.checks.some((c) => c.id === 'validity' && !c.ok);
  const ready =
    !!result?.read && !blocking.length && !result.duplicate && (!result.replaces || replace) && !saving && !checking;
  const suggestion = result?.checks.find((c) => c.id === 'class' && !c.ok)?.suggestion;

  async function save() {
    setSaving(true);
    setError('');
    try {
      const body = form();
      body.append('replace', String(replace));
      const r = await api<{ active: boolean }>(`/credentials/companies/${company}/certificates/upload`, 'POST', body);
      setPassword('');
      onSaved(
        r.active
          ? 'Firma guardada cifrada y activa.'
          : 'El certificado está vencido: se guardó cifrado sólo en el historial.',
      );
    } catch (e) {
      if (isLockedError(e)) vault.locked();
      else setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  function drop(e: DragEvent) {
    e.preventDefault();
    take(e.dataTransfer.files);
  }

  return (
    <Modal title="Agregar FIEL o CSD" onClose={onClose}>
      <div className="v2-addsig">
        <div className="v2-addsig-form">
          {!companyId && (
            <Field label="Empresa">
              <select value={company} onChange={(e) => setCompany(e.target.value)}>
                {allowed.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} · {c.rfc}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <fieldset className="v2-addsig-classes">
            <legend>¿De quién es la firma?</legend>
            {CLASSES.map((c) => (
              <label key={c.id} className={'v2-addsig-class' + (klass === c.id ? ' is-selected' : '')}>
                <input
                  type="radio"
                  name="signature-class"
                  value={c.id}
                  checked={klass === c.id}
                  onChange={() => setKlass(c.id)}
                />
                <span>
                  <strong>{c.label}</strong>
                  <small className="muted">{c.hint}</small>
                </span>
              </label>
            ))}
          </fieldset>
          <div
            className="v2-addsig-drop"
            onDragOver={(e) => e.preventDefault()}
            onDrop={drop}
            role="group"
            aria-label="Archivos .cer y .key"
          >
            <Upload size={20} aria-hidden />
            <p>
              Arrastra aquí el <strong>.cer</strong> y el <strong>.key</strong> juntos, o{' '}
              <button type="button" className="v2-link-button" onClick={() => input.current?.click()}>
                elígelos
              </button>
              .
            </p>
            <ul>
              <li>
                <FileKey2 size={14} aria-hidden /> Certificado: {cer ? cer.name : <span className="muted">falta</span>}
              </li>
              <li>
                <FileKey2 size={14} aria-hidden /> Clave privada:{' '}
                {key ? key.name : <span className="muted">falta</span>}
              </li>
            </ul>
            <input
              ref={input}
              type="file"
              accept=".cer,.key"
              multiple
              hidden
              aria-label="Elegir .cer y .key"
              onChange={(e) => {
                take(e.target.files);
                e.target.value = '';
              }}
            />
          </div>
          <Field label="Contraseña de la clave privada">
            <input type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
        </div>
        <aside className="v2-addsig-result" aria-live="polite" aria-label="Lo leído del certificado">
          {!result && !checking && (
            <p className="muted">Sube el .cer, el .key y escribe la contraseña para comprobarlos.</p>
          )}
          {checking && <p role="status">Comprobando…</p>}
          {result?.read && (
            <dl className="v2-addsig-read">
              <dt>Titular</dt>
              <dd>{result.read.holder_name || '—'}</dd>
              <dt>RFC</dt>
              <dd>
                {result.read.rfc}
                {result.read.representative_rfc && ` · representante ${result.read.representative_rfc}`}
              </dd>
              {result.read.curp && (
                <>
                  <dt>CURP</dt>
                  <dd>{result.read.curp}</dd>
                </>
              )}
              <dt>Número de certificado</dt>
              <dd className="mono">{result.read.number}</dd>
              <dt>Vigencia</dt>
              <dd>
                {result.read.valid_from.slice(0, 10)} a {result.read.valid_until.slice(0, 10)}
              </dd>
              {result.read.branch && (
                <>
                  <dt>Sucursal</dt>
                  <dd>{result.read.branch}</dd>
                </>
              )}
              <dt>Emisor</dt>
              <dd>{result.read.issuer}</dd>
            </dl>
          )}
          {result && (
            <ul className="v2-addsig-checks">
              {result.checks.map((c) => (
                <li key={c.id} className={c.ok ? 'is-ok' : c.blocking ? 'is-error' : 'is-warning'}>
                  {c.ok ? <CheckCircle2 size={16} aria-hidden /> : <XCircle size={16} aria-hidden />}
                  <span>
                    <strong>{CHECK_LABELS[c.id] || c.id}</strong> {c.message}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {suggestion && (
            <button type="button" className={stitchButton} onClick={() => setKlass(suggestion)}>
              Usar {CLASSES.find((c) => c.id === suggestion)?.label}
            </button>
          )}
          {result?.duplicate && (
            <p role="alert" className="error-banner">
              Ese certificado ya está guardado en esta empresa.
            </p>
          )}
          {result?.replaces && !blocking.length && (
            <label className="check-option">
              <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> Ya hay una FIEL
              activa de esa clase: reemplazarla (la anterior pasa al historial)
            </label>
          )}
          {expired && !blocking.length && (
            <p className="muted small">Está vencido: se guardará sólo en el historial y no quedará activo.</p>
          )}
        </aside>
      </div>
      {result?.sat_access && klass !== 'CSD' && (
        <section className="v2-addsig-sat" aria-label="Lista para «Acceso con e.firma» del SAT">
          <h3>
            <ShieldCheck size={16} aria-hidden /> Lista para «Acceso con e.firma» del SAT
          </h3>
          <dl>
            <dt>Certificado (.cer)</dt>
            <dd>{result.sat_access.cer}</dd>
            <dt>Clave privada (.key)</dt>
            <dd>{result.sat_access.key}</dd>
            <dt>Contraseña de clave privada</dt>
            <dd aria-label="Contraseña oculta">{result.sat_access.password}</dd>
            <dt>RFC</dt>
            <dd>{result.sat_access.rfc}</dd>
          </dl>
        </section>
      )}
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="button" className={stitchButton} onClick={onClose}>
          Cancelar
        </button>
        <button type="button" className={stitchPrimary} disabled={!ready} onClick={save}>
          {saving ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </Modal>
  );
}
