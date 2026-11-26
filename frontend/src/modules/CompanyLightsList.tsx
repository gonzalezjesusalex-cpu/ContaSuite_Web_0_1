import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { Badge, Empty } from '../components/ui';
import { stitchCard } from '../components/stitch';
import { describe, ICONS, STATE_TEXT, stateText, type Light } from './DocumentLights';
import { DOC_KINDS, DOC_LABEL, SEVERITY_ORDER, savedSoon, type DocStatus } from './DocumentSummary';

const TONE: Record<Light['state'], string> = {
  red: 'red',
  amber: 'amber',
  gray: 'neutral',
  green: 'green',
  na: 'neutral',
};
const OPINION: Record<string, string> = { positive: 'Positivas', negative: 'Negativas', none: 'Sin opinión' };
const opinionOf = (l: Light) => (l.result === 'positive' ? 'positive' : l.result === 'negative' ? 'negative' : 'none');

/** Documentos › Semáforo (por documento y estado) y Documentos › Opiniones (opinión SAT por resultado): las
 *  luces del semáforo de cada empresa, filtradas desde la URL (`doc`, `estado`) para que las tarjetas y las
 *  celdas del Resumen lleguen ya filtradas. «riesgo» = vencidos y por vencer dentro del plazo elegido. */
export default function CompanyLightsList({ mode, userId }: { mode: 'semaforo' | 'opiniones'; userId: string }) {
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<DocStatus | null>(null);
  const [error, setError] = useState('');
  const soon = savedSoon(userId);
  const doc = mode === 'opiniones' ? 'sat' : (params.get('doc') as Light['kind'] | null) || '';
  const estado = params.get('estado') || '';
  useEffect(() => {
    const abort = new AbortController();
    api<DocStatus>('/integral/document-status?soon=' + soon, 'GET', undefined, abort.signal)
      .then(setData)
      .catch((e) => !abort.signal.aborted && setError(e.message));
    return () => abort.abort();
  }, [soon]);
  const setFilter = (key: string, value: string) =>
    setParams(
      (previous) => {
        const q = new URLSearchParams(previous);
        if (value) q.set(key, value);
        else q.delete(key);
        return q;
      },
      { replace: true },
    );
  const today = new Date().toISOString().slice(0, 10);
  const limit = new Date(Date.now() + soon * 86400000).toISOString().slice(0, 10);
  const matches = (l: Light) => {
    if (doc && l.kind !== doc) return false;
    if (mode === 'opiniones') return !estado || opinionOf(l) === estado;
    if (estado === 'riesgo') return l.state === 'red' || (!!l.expires && l.expires >= today && l.expires <= limit);
    return !estado || l.state === estado;
  };
  const rows = (data?.companies || []).flatMap((c) => c.lights.filter(matches).map((l) => ({ company: c, light: l })));
  const order = (l: Light) => SEVERITY_ORDER.indexOf(l.state);
  rows.sort((a, b) => order(a.light) - order(b.light) || a.company.name.localeCompare(b.company.name, 'es'));
  return (
    <section className={stitchCard + ' padded stitch-live-module'}>
      <div className="card-title">
        <div>
          <h2>{mode === 'opiniones' ? 'Opiniones de cumplimiento SAT' : 'Semáforo por empresa'}</h2>
          <p className="muted">Según los documentos cargados; no consulta al SAT ni al IMSS.</p>
        </div>
      </div>
      <div className="toolbar">
        {mode === 'semaforo' && (
          <select aria-label="Documento" value={doc} onChange={(e) => setFilter('doc', e.target.value)}>
            <option value="">Todos los documentos</option>
            {DOC_KINDS.map((k) => (
              <option key={k} value={k}>
                {DOC_LABEL[k]}
              </option>
            ))}
          </select>
        )}
        <select aria-label="Estado" value={estado} onChange={(e) => setFilter('estado', e.target.value)}>
          <option value="">Todos los estados</option>
          {mode === 'opiniones' ? (
            Object.entries(OPINION).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))
          ) : (
            <>
              <option value="riesgo">En riesgo (vencidos y por vencer en {soon} días)</option>
              {SEVERITY_ORDER.map((st) => (
                <option key={st} value={st}>
                  {STATE_TEXT[st]}
                </option>
              ))}
            </>
          )}
        </select>
      </div>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {!data && !error && <p role="status">Consultando semáforo…</p>}
      {data &&
        (rows.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Empresa</th>
                  <th scope="col">RFC</th>
                  <th scope="col">Documento</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Detalle</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ company: c, light: l }) => {
                  const Icon = ICONS[l.kind];
                  return (
                    <tr key={c.company_id + l.kind}>
                      <td>
                        <Link to={'/empresas/' + c.company_id + '?tab=Documentos'}>{c.name}</Link>
                      </td>
                      <td className="rfc">{c.rfc}</td>
                      <td>
                        <Icon size={15} aria-hidden /> {DOC_LABEL[l.kind]}
                      </td>
                      <td>
                        <Badge tone={TONE[l.state]}>{stateText(l)}</Badge>
                      </td>
                      <td className="muted">{describe(l).split(' · ').slice(1).join(' · ')}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="Sin documentos en este filtro">Cambia el documento o el estado.</Empty>
        ))}
    </section>
  );
}
