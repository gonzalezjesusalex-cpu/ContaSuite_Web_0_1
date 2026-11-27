import { useEffect, useState } from 'react';
import { ArrowUp, FileText, Folder, Lock as LockIcon, RefreshCw } from 'lucide-react';
import { Badge, Modal } from '../../components/ui';
import { stitchButton, stitchPrimary } from '../../components/stitch';
import { folderOp, lockText, type CompanyFolder, type Listing } from './folderJobs';

type Tab = 'equipo' | 'red' | 'recientes';

/** Selector de carpeta servido por el agente: sólo navega dentro de las raíces autorizadas. */
export default function FolderPicker({
  companyId,
  companyName,
  year,
  info,
  onClose,
  onChoose,
}: {
  companyId: string;
  companyName: string;
  year: number;
  info: CompanyFolder;
  onClose: () => void;
  onChoose: (path: string, origin: string, link: boolean) => void;
}) {
  const local = info.raices.filter((r) => !r.startsWith('\\\\'));
  const network = info.raices.filter((r) => r.startsWith('\\\\'));
  const [tab, setTab] = useState<Tab>(info.ruta?.startsWith('\\\\') ? 'red' : local.length ? 'equipo' : 'red');
  const [typed, setTyped] = useState(info.ruta || '');
  const [listing, setListing] = useState<Listing | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [link, setLink] = useState(true);

  async function open(path: string) {
    if (!path.trim()) return;
    setBusy(true);
    setError('');
    try {
      const result = await folderOp<Listing>(companyId, 'listar', path.trim(), info.plantilla);
      setListing(result);
      setTyped(result.ruta); // una unidad mapeada (Z:\…) vuelve convertida a su ruta de red real
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (info.ruta) void open(info.ruta);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const roots = tab === 'equipo' ? local : tab === 'red' ? network : info.recientes;
  const crumbs = listing ? crumbsOf(listing.ruta, info.raices) : [];
  const foreign = listing?.bloqueo.estado === 'ajeno';
  const origin = listing?.ruta.startsWith('\\\\') ? 'red' : 'equipo';
  return (
    <Modal title="Elegir carpeta" onClose={onClose}>
      <div className="declara-picker">
        <div className="declara-tabs" role="tablist" aria-label="Origen de la carpeta">
          {(
            [
              ['equipo', 'Este equipo'],
              ['red', 'Red local'],
              ['recientes', `Recientes de ${companyName}`],
            ] as [Tab, string][]
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              className={'declara-tab' + (tab === id ? ' active' : '')}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <ul className="declara-picker-roots">
          {roots.map((r) => (
            <li key={r}>
              <button type="button" className={stitchButton} onClick={() => void open(r)} disabled={busy}>
                <Folder size={15} />
                {r}
              </button>
            </li>
          ))}
          {!roots.length && (
            <li className="muted">
              {tab === 'recientes'
                ? 'Sin carpetas recientes para esta empresa.'
                : 'No hay carpetas autorizadas de este tipo: las define la administración.'}
            </li>
          )}
        </ul>
        <form
          className="declara-path-row"
          onSubmit={(e) => {
            e.preventDefault();
            void open(typed);
          }}
        >
          <label className="sr-only" htmlFor="declara-path">
            Ruta
          </label>
          <input
            id="declara-path"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder="\\SERVIDOR\Clientes\… o Z:\…"
            spellCheck={false}
          />
          <button type="submit" className={stitchButton} disabled={busy}>
            {busy ? <RefreshCw size={15} className="recopila-spinner" /> : 'Ir'}
          </button>
        </form>
        {error && <p className="declara-msg error">{error}</p>}
        {listing && (
          <>
            <nav className="declara-crumbs" aria-label="Ruta de navegación">
              {crumbs.map((c, i) => (
                <span key={c.path}>
                  {i > 0 && <span aria-hidden="true"> › </span>}
                  <button
                    type="button"
                    className="declara-crumb"
                    disabled={busy || i === crumbs.length - 1}
                    onClick={() => void open(c.path)}
                  >
                    {c.label}
                  </button>
                </span>
              ))}
            </nav>
            <p className="muted">
              {listing.pdf} PDF en esta carpeta · {lockText(listing.bloqueo)}
            </p>
            <ul className="declara-folder-list">
              {listing.padre && (
                <li>
                  <button type="button" disabled={busy} onClick={() => void open(listing.padre!)}>
                    <ArrowUp size={15} />
                    Subir un nivel
                  </button>
                </li>
              )}
              {listing.carpetas.map((f) => (
                <li key={f.ruta}>
                  <button type="button" disabled={busy || !f.legible} onClick={() => void open(f.ruta)}>
                    <Folder size={15} />
                    <span className="declara-folder-name">{f.nombre}</span>
                    <span className="declara-folder-tags">
                      <span>
                        <FileText size={13} /> {f.pdf} PDF
                      </span>
                      {f.indice && <Badge tone="blue">Con índice de Declara</Badge>}
                      {f.plantilla && <Badge tone="green">Coincide con la plantilla</Badge>}
                      {!f.legible && <Badge tone="red">Sin acceso</Badge>}
                      {f.bloqueo.estado === 'ajeno' && (
                        <Badge tone="amber">
                          <LockIcon size={12} /> {lockText(f.bloqueo)}
                        </Badge>
                      )}
                    </span>
                  </button>
                </li>
              ))}
              {!listing.carpetas.length && <li className="muted">Sin subcarpetas.</li>}
            </ul>
          </>
        )}
        <p className="muted">Acceso a la red: sesión de Windows de este equipo.</p>
        <label className="declara-check">
          <input type="checkbox" checked={link} onChange={(e) => setLink(e.target.checked)} />
          Vincular esta carpeta a {companyName} · {year}
        </label>
        <div className="actions">
          <button type="button" className={stitchButton} onClick={onClose}>
            Cancelar
          </button>
          <button
            type="button"
            className={stitchPrimary}
            disabled={!listing || busy}
            onClick={() => listing && onChoose(listing.ruta, origin, link)}
          >
            Usar esta carpeta
          </button>
        </div>
        {foreign && <p className="declara-msg warn">La carpeta está en uso: podrás analizarla, pero no renombrar.</p>}
      </div>
    </Modal>
  );
}

function crumbsOf(path: string, roots: string[]) {
  const norm = (p: string) => p.replace(/\\+$/, '').toLowerCase();
  const root = roots
    .filter((r) => norm(path) === norm(r) || norm(path).startsWith(norm(r) + '\\'))
    .sort((a, b) => b.length - a.length)[0];
  if (!root) return [{ label: path, path }];
  const base = root.replace(/\\+$/, '');
  const rest = path.slice(base.length).split('\\').filter(Boolean);
  const crumbs = [{ label: base, path: base }];
  let current = base;
  for (const part of rest) {
    current = current + '\\' + part;
    crumbs.push({ label: part, path: current });
  }
  return crumbs;
}
