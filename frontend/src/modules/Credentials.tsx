import PasswordManager from './PasswordManager';
import CertificateLifecycle from './CertificateLifecycle';
import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { Field, Modal, Kpi } from '../components/ui';
import { stitchButton, stitchPrimary, stitchCard } from '../components/stitch';
import type { Job, State } from '../types';
import DetectedCertificates from './DetectedCertificates';
import { isLockedError, useVault } from './VaultGate';
type Secret = { id: string; service_id: string; label: string; revision: number; archived: boolean };
type Cert = {
  id: string;
  kind: string;
  valid_until: string | null;
  days_remaining: number | null;
  state: string;
  reviewed_at: string;
  rfc: string;
};
type Snapshot = {
  credentials: Secret[];
  certificates: Cert[];
  services: { id: string; label: string }[];
  permissions: string[];
  reveal_enabled: boolean;
};
const statuses: Record<string, string> = {
  valid: 'Vigente por fecha',
  expiring: 'Próximo a vencer',
  expired: 'Vencido por fecha',
  unknown: 'Sin información',
  pending_verification: 'Pendiente de verificación',
};
export default function Credentials({
  state,
  companyId,
  scanJob,
}: {
  state: State;
  companyId?: string;
  scanJob?: Job;
}) {
  const vault = useVault();
  const [company, setCompany] = useState(companyId || ''),
    [data, setData] = useState<Snapshot | null>(null),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(false),
    [reload, setReload] = useState(0),
    [tab, setTab] = useState('Resumen'),
    [regime, setRegime] = useState(''),
    [kind, setKind] = useState(''),
    [status, setStatus] = useState(''),
    [until, setUntil] = useState('');
  const [busy, setBusy] = useState(false),
    [certOpen, setCertOpen] = useState(false),
    [documentId, setDocumentId] = useState(''),
    [certKind, setCertKind] = useState('unknown'),
    [history, setHistory] = useState<unknown[] | null>(null),
    [message, setMessage] = useState('');
  useEffect(() => {
    setCompany(companyId || '');
  }, [companyId]);
  useEffect(() => {
    setData(null);
    setError('');
    setHistory(null);
    if (!company) return;
    const c = new AbortController();
    setLoading(true);
    api<Snapshot>('/credentials/companies/' + company, 'GET', undefined, c.signal)
      .then(setData)
      .catch((e) => {
        if (c.signal.aborted) return;
        if (isLockedError(e)) vault.locked();
        else setError(e.message);
      })
      .finally(() => {
        if (!c.signal.aborted) setLoading(false);
      });
    return () => c.abort();
  }, [company, reload, vault]);
  const can = (p: string) => data?.permissions.includes(p) || false;
  const certs = (data?.certificates || []).filter(
    (c) =>
      (!kind || c.kind === kind) &&
      (!status || c.state === status) &&
      (!until || (c.valid_until && c.valid_until.slice(0, 10) <= until)) &&
      (tab !== 'FIEL' || c.kind === 'fiel') &&
      (tab !== 'CSD' || c.kind === 'csd'),
  );
  async function saveCert(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api('/credentials/companies/' + company + '/certificates', 'POST', {
        kind: certKind,
        document_id: documentId || null,
      });
      setCertOpen(false);
      setDocumentId('');
      setReload((n) => n + 1);
      setMessage('Referencia registrada; sin validación ante el SAT.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className={stitchCard + ' padded stitch-live-module'}>
      <h2>Credenciales y Certificados</h2>
      <p>
        Contraseñas cifradas con la contraseña maestra de la bóveda, archivos FIEL/CSD y vigencia de certificados
        públicos (sin validación ante el SAT).
      </p>
      <PasswordManager
        companyId={companyId || company || undefined}
        notify={setMessage}
        users={Object.fromEntries([
          ...(state.responsibles || []).map((r) => [r.id, r.display_name]),
          [state.current_user.id, state.current_user.display_name],
        ])}
      />
      {!companyId && (
        <div className="toolbar">
          <select
            aria-label="Régimen"
            value={regime}
            onChange={(e) => {
              setRegime(e.target.value);
              setCompany('');
            }}
          >
            <option value="">Todos los regímenes</option>
            {[...new Set(state.companies.map((c) => c.regime))].map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
          <select aria-label="Empresa de credenciales" value={company} onChange={(e) => setCompany(e.target.value)}>
            <option value="">Selecciona una empresa</option>
            {state.companies
              .filter((c) => !regime || c.regime === regime)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} · {c.rfc}
                </option>
              ))}
          </select>
        </div>
      )}
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {loading && <p role="status">Consultando metadatos…</p>}
      {data && (
        <>
          <CertificateLifecycle
            key={company}
            companyId={company}
            certificates={data.certificates}
            canWrite={can('certificates')}
            archived={!!state.companies.find((c) => c.id === company)?.archived}
          />
          <DetectedCertificates
            job={scanJob}
            canRegister={can('certificates')}
            onRegister={(k) => {
              setCertKind(k);
              setCertOpen(true);
            }}
          />
          <div className="tabs">
            {['Resumen', 'Accesos fiscales', 'FIEL', 'CSD', 'IMSS e INFONAVIT', 'Otros servicios', 'Historial'].map(
              (t) => (
                <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
                  {t}
                </button>
              ),
            )}
          </div>
          <div className="kpi-grid four">
            <Kpi
              label="Empresa con certificados"
              value={data.certificates.length ? 1 : 0}
              detail="Empresa seleccionada"
            />
            <Kpi
              label="FIEL próximas"
              value={data.certificates.filter((c) => c.kind === 'fiel' && c.state === 'expiring').length}
              detail="Vigencia temporal"
            />
            <Kpi
              label="CSD próximos"
              value={data.certificates.filter((c) => c.kind === 'csd' && c.state === 'expiring').length}
              detail="Vigencia temporal"
            />
            <Kpi
              label="Vencidos por fecha"
              value={data.certificates.filter((c) => c.state === 'expired').length}
              detail="Sin consulta de revocación"
            />
            <Kpi
              label="Sin vigencia conocida"
              value={data.certificates.filter((c) => c.state === 'unknown').length}
              detail="Requieren revisión"
            />
            <Kpi
              label="Información incompleta"
              value={
                !data.certificates.length ||
                data.certificates.some((c) => c.state === 'unknown' || c.kind === 'unknown')
                  ? 1
                  : 0
              }
              detail="Empresa seleccionada"
            />
          </div>
          {tab === 'Historial' ? (
            <>
              <button
                className={stitchButton}
                disabled={!can('history')}
                onClick={async () => {
                  try {
                    setHistory(await api<unknown[]>('/credentials/companies/' + company + '/history'));
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                Consultar historial
              </button>
              {history && (
                <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                  {JSON.stringify(history, null, 2)}
                </pre>
              )}
            </>
          ) : (
            <>
              <div className="actions">
                <button className={stitchButton} disabled={!can('certificates')} onClick={() => setCertOpen(true)}>
                  Registrar certificado / vínculo
                </button>
                <Link className={stitchButton} to={'/empresas/' + company + '?tab=Documentos'}>
                  Documentos de la empresa
                </Link>
              </div>
              <h3>Certificados públicos</h3>
              <div className="toolbar">
                <select aria-label="Tipo de certificado" value={kind} onChange={(e) => setKind(e.target.value)}>
                  <option value="">Todos los tipos</option>
                  {['fiel', 'csd', 'unknown'].map((k) => (
                    <option key={k}>{k}</option>
                  ))}
                </select>
                <select aria-label="Estado del certificado" value={status} onChange={(e) => setStatus(e.target.value)}>
                  <option value="">Todos los estados</option>
                  {Object.entries(statuses).map(([id, l]) => (
                    <option key={id} value={id}>
                      {l}
                    </option>
                  ))}
                </select>
                <label>
                  Vence hasta
                  <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
                </label>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      {['Empresa', 'RFC', 'Tipo', 'Vence', 'Días', 'Estado', 'Última revisión', 'Acciones'].map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {certs.map((c) => (
                      <tr key={c.id}>
                        <td>{state.companies.find((x) => x.id === company)?.name}</td>
                        <td>{c.rfc}</td>
                        <td>{c.kind}</td>
                        <td>{c.valid_until?.slice(0, 10) || 'Sin información'}</td>
                        <td>{c.days_remaining ?? '—'}</td>
                        <td>{statuses[c.state]}</td>
                        <td>{c.reviewed_at.slice(0, 10)}</td>
                        <td>
                          <Link to={'/empresas/' + company + '?tab=Documentos'}>Expediente documental</Link>
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
      {certOpen && (
        <Modal
          title="Certificado público"
          onClose={() => {
            if (!busy) setCertOpen(false);
          }}
        >
          <form className="padded" onSubmit={saveCert}>
            <Field label="Tipo declarado por el despacho">
              <select value={certKind} onChange={(e) => setCertKind(e.target.value)}>
                <option value="unknown">Pendiente de verificación</option>
                <option value="fiel">FIEL</option>
                <option value="csd">CSD</option>
              </select>
            </Field>
            <Field label="ID documental CER (opcional)">
              <input maxLength={36} value={documentId} onChange={(e) => setDocumentId(e.target.value)} />
            </Field>
            <p>
              Sin documento se registra información pendiente. Sólo se analiza CER público; nunca KEY. El nombre no
              determina el tipo.
            </p>
            <button className={stitchPrimary} disabled={busy}>
              Registrar referencia
            </button>
          </form>
        </Modal>
      )}
    </section>
  );
}
