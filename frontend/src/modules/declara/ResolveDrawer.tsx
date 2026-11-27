import { useEffect, useRef, useState } from 'react';
import { ExternalLink, FileText, X } from 'lucide-react';
import { api, getToken } from '../../api';
import { Badge } from '../../components/ui';
import { stitchButton, stitchDanger, stitchPrimary } from '../../components/stitch';
import {
  FORBIDDEN,
  MONTHS,
  MONTH_STATES,
  STATUS_LABELS,
  STATUS_TONES,
  documentLabel,
  fileName,
  monthLabel,
  type Detail,
  type PdfRecord,
  type Preview,
} from './model';

type Option = 'duplicate' | 'type' | 'manual';
type Kind = 'DECLARACION' | 'ACUSE';
type Type = 'NORMAL' | 'COMPLEMENTARIA';

function Selectors({
  kind,
  type,
  month,
  onKind,
  onType,
  onMonth,
  disabled,
}: {
  kind: Kind;
  type: Type;
  month: string;
  onKind: (v: Kind) => void;
  onType: (v: Type) => void;
  onMonth: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="declara-selectors">
      <label>
        Documento
        <select value={kind} disabled={disabled} onChange={(e) => onKind(e.target.value as Kind)}>
          <option value="DECLARACION">Declaración</option>
          <option value="ACUSE">Acuse</option>
        </select>
      </label>
      <label>
        Tipo
        <select value={type} disabled={disabled} onChange={(e) => onType(e.target.value as Type)}>
          <option value="NORMAL">Normal</option>
          <option value="COMPLEMENTARIA">Complementaria</option>
        </select>
      </label>
      <label>
        Mes
        <select value={month} disabled={disabled} onChange={(e) => onMonth(e.target.value)}>
          <option value="">Elige el mes</option>
          {MONTHS.map((m, i) => (
            <option key={m} value={m}>
              {i + 1}. {monthLabel(m)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

const stem = (name: string | null) => (name || '').replace(/\.pdf$/i, '');

/** Panel lateral «Resolver archivo». Nada se escribe en disco: sólo cambia el plan. */
export default function ResolveDrawer({
  runId,
  revision,
  editable,
  record,
  records,
  onClose,
  onApplied,
}: {
  runId: string;
  revision: number;
  editable: boolean;
  record: PdfRecord;
  records: PdfRecord[];
  onClose: () => void;
  onApplied: (detail: Detail, message: string) => void;
}) {
  const foreign = record.status === 'RFC DIFERENTE';
  const excluded = record.status === 'EXCLUIDO';
  const correct = record.status === 'CORRECTO';
  const canDuplicate = !correct && !!record.month && !!record.document_kind;
  const [option, setOption] = useState<Option>(
    record.status === 'COPIA IDÉNTICA' && canDuplicate ? 'duplicate' : correct ? 'manual' : 'type',
  );
  const initialKind = (record.document_kind as Kind) || 'DECLARACION';
  const initialType = ((record.declaration_type || 'Normal').toUpperCase() as Type) || 'NORMAL';
  const [kind, setKind] = useState<Kind>(initialKind);
  const [type, setType] = useState<Type>(initialType);
  const [month, setMonth] = useState(record.month || '');
  const [name, setName] = useState(stem(record.expected_name) || stem(fileName(record.path)));
  const [count, setCount] = useState(true);
  const [mKind, setMKind] = useState<Kind>(initialKind);
  const [mType, setMType] = useState<Type>(initialType);
  const [mMonth, setMMonth] = useState(record.month || '');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [pdf, setPdf] = useState('');
  const [pdfError, setPdfError] = useState('');
  const detected = useRef('');
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    panel.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    const controller = new AbortController();
    let url = '';
    fetch(`/api/declara/runs/${runId}/file/${record.index}`, {
      headers: { Authorization: 'Bearer ' + getToken() },
      signal: controller.signal,
    })
      .then(async (r) => {
        if (!r.ok) throw new Error('No se pudo abrir el PDF.');
        url = URL.createObjectURL(await r.blob());
        if (!controller.signal.aborted) setPdf(url);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setPdfError(e.message);
      });
    return () => {
      controller.abort();
      URL.revokeObjectURL(url);
    };
  }, [runId, record.index]);

  const body = () =>
    option === 'duplicate'
      ? { index: record.index, action: 'duplicate' }
      : option === 'type'
        ? { index: record.index, action: 'type', choice: `${kind} ${type}`, month }
        : {
            index: record.index,
            action: 'manual',
            name,
            count,
            choice: count ? `${mKind} ${mType}` : '',
            month: count ? mMonth : '',
          };

  // Validación en vivo: el servidor calcula el nombre final, los choques y el efecto en el mes.
  const localError =
    option === 'manual' && FORBIDDEN.test(name) ? 'No se permiten los caracteres < > : " / \\ | ? *' : '';
  useEffect(() => {
    if (!editable || foreign || excluded || (option === 'type' && !month)) {
      setPreview(null);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setChecking(true);
      api<Preview>(`/declara/runs/${runId}/preview`, 'POST', body(), controller.signal)
        .then((p) => {
          setPreview(p);
          if (option === 'manual' && p.standard && p.standard.texto !== detected.current) {
            detected.current = p.standard.texto;
            setMKind(p.standard.document_kind as Kind);
            setMType(p.standard.declaration_type.toUpperCase() as Type);
            setMMonth(p.standard.month);
          }
        })
        .catch(() => undefined)
        .finally(() => setChecking(false));
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [option, kind, type, month, name, count, mKind, mType, mMonth, editable]);

  async function send(data: object, message: string) {
    setSaving(true);
    setError('');
    try {
      const detail = await api<Detail>(`/declara/runs/${runId}/resolve`, 'POST', { revision, ...data });
      onApplied(detail, message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const twins = records.filter((r) => r.index !== record.index && r.sha256 && r.sha256 === record.sha256);
  const fingerprint = record.identical_to
    ? `Igual a ${record.identical_to}`
    : twins.length
      ? `Igual a ${twins.map((t) => fileName(t.path)).join(', ')}`
      : 'Única';
  const problems = [...(localError ? [localError] : []), ...(preview?.errors || [])];
  const finalName =
    option === 'manual' ? (name.trim() ? name.trim().replace(/\.pdf$/i, '') + '.pdf' : '') : preview?.name;
  const effect = preview?.effect;
  const blocked = !editable || foreign || excluded;
  const canApply =
    !blocked && !saving && !checking && !problems.length && !!preview?.name && !(option === 'type' && !month);

  return (
    <div className="declara-drawer-layer">
      <button type="button" className="declara-drawer-shade" aria-label="Cerrar panel" onClick={onClose} />
      <aside
        className="declara-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="declara-drawer-title"
        ref={panel}
        tabIndex={-1}
      >
        <header className="declara-drawer-head">
          <div>
            <h2 id="declara-drawer-title">Resolver archivo</h2>
            <p className="declara-drawer-file">{fileName(record.path)}</p>
            <Badge tone={STATUS_TONES[record.status] || 'neutral'}>
              {STATUS_LABELS[record.status] || record.status}
              {!['RENOMBRAR', 'CORRECTO'].includes(record.status) && record.detail ? ' · ' + record.detail : ''}
            </Badge>
          </div>
          <button type="button" className={stitchButton + ' icon-only'} onClick={onClose} aria-label="Cerrar">
            <X size={18} />
          </button>
        </header>

        <div className="declara-drawer-body">
          <section className="declara-drawer-preview">
            {pdf ? (
              <iframe title="Página 1 del PDF" src={pdf + '#page=1&toolbar=0&navpanes=0&view=FitH'} />
            ) : (
              <div className="empty">
                <FileText size={28} />
                <p>{pdfError || 'Cargando PDF…'}</p>
              </div>
            )}
            <button type="button" className={stitchButton} disabled={!pdf} onClick={() => window.open(pdf, '_blank')}>
              <ExternalLink size={15} />
              Abrir PDF completo
            </button>
          </section>

          <section>
            <h3>Datos detectados</h3>
            <dl className="declara-facts">
              <dt>Documento</dt>
              <dd>{documentLabel(record)}</dd>
              <dt>Periodo</dt>
              <dd>
                {record.month ? monthLabel(record.month) : 'Sin detectar'} {record.year || ''}
                {record.other_year && ' · Ejercicio distinto'}
              </dd>
              <dt>RFC</dt>
              <dd>{record.rfc || 'Sin detectar'}</dd>
              <dt>Nº operación</dt>
              <dd className="declara-mono">{record.operation || 'Sin detectar'}</dd>
              <dt>Huella</dt>
              <dd>{fingerprint}</dd>
            </dl>
          </section>

          {foreign && (
            <p className="recopila-warning">
              Este PDF es de otro RFC: no se puede incluir en esta empresa. Puedes excluirlo del plan.
            </p>
          )}
          {excluded && (
            <p className="recopila-warning">{record.detail} Reincluye el archivo para volver a resolverlo.</p>
          )}
          {!editable && !foreign && !excluded && (
            <p className="muted">El plan ya se aplicó o está en curso: sólo lectura.</p>
          )}

          {!blocked && (
            <fieldset className="declara-options" disabled={saving}>
              <legend>¿Qué hacemos con este archivo?</legend>
              <label className={'declara-option' + (option === 'duplicate' ? ' active' : '')}>
                <input
                  type="radio"
                  name="declara-option"
                  checked={option === 'duplicate'}
                  disabled={!canDuplicate}
                  onChange={() => setOption('duplicate')}
                />
                <span>
                  <strong>Es otra copia válida del mismo documento</strong>
                  <small>
                    {canDuplicate
                      ? 'Recibe el siguiente sub-consecutivo libre.'
                      : 'Requiere que el periodo y el tipo sean conocidos.'}
                  </small>
                </span>
              </label>
              <label className={'declara-option' + (option === 'type' ? ' active' : '')}>
                <input
                  type="radio"
                  name="declara-option"
                  checked={option === 'type'}
                  disabled={correct}
                  onChange={() => setOption('type')}
                />
                <span>
                  <strong>El tipo o periodo está mal: corregirlo</strong>
                  <small>Si el nombre resultante está ocupado se asigna consecutivo automáticamente.</small>
                </span>
              </label>
              {option === 'type' && (
                <Selectors kind={kind} type={type} month={month} onKind={setKind} onType={setType} onMonth={setMonth} />
              )}
              <label className={'declara-option' + (option === 'manual' ? ' active' : '')}>
                <input
                  type="radio"
                  name="declara-option"
                  checked={option === 'manual'}
                  onChange={() => setOption('manual')}
                />
                <span>
                  <strong>Renombrar manualmente</strong>
                  <small>Escribe el nombre sin extensión; «.pdf» se agrega solo.</small>
                </span>
              </label>
              {option === 'manual' && (
                <div className="declara-manual">
                  <label className="declara-name-input">
                    Nombre
                    <span>
                      <input
                        value={name}
                        maxLength={250}
                        onChange={(e) => setName(e.target.value)}
                        aria-invalid={problems.length > 0}
                        aria-describedby="declara-name-help"
                      />
                      <em>.pdf</em>
                    </span>
                  </label>
                  <div id="declara-name-help" aria-live="polite">
                    {problems.map((p) => (
                      <p key={p} className="declara-msg error">
                        {p}
                      </p>
                    ))}
                    {!problems.length &&
                      preview?.warnings.map((w) => (
                        <p key={w} className="declara-msg warn">
                          {w}
                        </p>
                      ))}
                    {!problems.length && preview?.standard && (
                      <p className="declara-msg ok">{preview.standard.texto}</p>
                    )}
                  </div>
                  <label className="declara-check">
                    <input type="checkbox" checked={count} onChange={(e) => setCount(e.target.checked)} />
                    Contarlo en el control mensual
                  </label>
                  {count ? (
                    <Selectors
                      kind={mKind}
                      type={mType}
                      month={mMonth}
                      onKind={setMKind}
                      onType={setMType}
                      onMonth={setMMonth}
                    />
                  ) : (
                    <small className="muted">Se renombra con el nombre dado, pero no cuenta en la matriz.</small>
                  )}
                </div>
              )}
              {option !== 'manual' &&
                preview?.errors.map((p) => (
                  <p key={p} className="declara-msg error">
                    {p}
                  </p>
                ))}
            </fieldset>
          )}

          {!blocked && (
            <section className="declara-final-box" aria-live="polite">
              <span>Nombre final en el plan</span>
              <strong>{checking ? 'Calculando…' : finalName || '—'}</strong>
              {effect && (
                <small>
                  {monthLabel(effect.month)}{' '}
                  {effect.before === effect.after
                    ? `seguiría en ${MONTH_STATES[effect.after].label}`
                    : `pasaría a ${MONTH_STATES[effect.after].label}`}
                </small>
              )}
            </section>
          )}
          {error && (
            <p className="declara-msg error" role="alert">
              {error}
            </p>
          )}
        </div>

        <footer className="declara-drawer-foot">
          {editable && !excluded && (
            <button
              type="button"
              className={stitchDanger}
              disabled={saving}
              onClick={() => send({ index: record.index, action: 'exclude' }, 'Archivo excluido del plan.')}
            >
              Excluir del plan
            </button>
          )}
          {editable && excluded && (
            <button
              type="button"
              className={stitchButton}
              disabled={saving}
              onClick={() => send({ index: record.index, action: 'include' }, 'Archivo reincluido en el plan.')}
            >
              Reincluir en el plan
            </button>
          )}
          <span className="declara-foot-gap" />
          <button type="button" className={stitchButton} onClick={onClose}>
            Cancelar
          </button>
          {!blocked && (
            <button
              type="button"
              className={stitchPrimary}
              disabled={!canApply}
              onClick={() => send(body(), 'Cambio aplicado al plan. Nada se escribió en disco.')}
            >
              {saving ? 'Guardando…' : 'Aplicar al plan'}
            </button>
          )}
        </footer>
      </aside>
    </div>
  );
}
