import { useEffect, useState, type ReactNode } from 'react';
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen, Link2, RefreshCw, Search } from 'lucide-react';
import { api } from '../api';
import { Empty, MiddleText } from '../components/ui';

export type BranchFile = {
  id: string;
  name: string;
  path: string;
  virtual_path: string;
  size: number;
  section: string;
  state: string;
  change: string;
  document_id: string | null;
  revision: number | null;
};
type Level = {
  prefix: string;
  folders: { name: string; path: string; files: number }[];
  files: BranchFile[];
  more: boolean;
  total: number;
};

/** The company's virtual folder tree (persistent index from the local agent), one level at a time.
 * Files whose bytes match a registered document are linked to it so the document center can preview the original. */
export default function VirtualBranch({
  companyId,
  selected,
  onSelect,
}: {
  companyId: string;
  selected: string;
  onSelect: (file: BranchFile) => void;
}) {
  const [levels, setLevels] = useState<Record<string, Level>>({});
  const [open, setOpen] = useState<Set<string>>(new Set(['']));
  const [loading, setLoading] = useState<Set<string>>(new Set());
  const [error, setError] = useState('');
  const [q, setQ] = useState('');
  const [found, setFound] = useState<Level | null>(null);
  const [reload, setReload] = useState(0);

  async function load(prefix: string, signal?: AbortSignal) {
    setLoading((s) => new Set(s).add(prefix));
    try {
      const params = new URLSearchParams({ prefix });
      const level = await api<Level>(`/companies/${companyId}/virtual-index/tree?${params}`, 'GET', undefined, signal);
      if (!signal?.aborted) setLevels((l) => ({ ...l, [prefix]: level }));
    } catch (e) {
      if (!signal?.aborted) setError((e as Error).message);
    } finally {
      setLoading((s) => {
        const n = new Set(s);
        n.delete(prefix);
        return n;
      });
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    setLevels({});
    setOpen(new Set(['']));
    setError('');
    void load('', controller.signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId, reload]);
  useEffect(() => {
    setFound(null);
    if (q.trim().length < 2) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api<Level>(
        `/companies/${companyId}/virtual-index/tree?` + new URLSearchParams({ q: q.trim() }),
        'GET',
        undefined,
        controller.signal,
      )
        .then((r) => {
          if (!controller.signal.aborted) setFound(r);
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(e.message);
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [companyId, q]);

  function toggle(path: string) {
    const next = new Set(open);
    if (next.has(path)) next.delete(path);
    else {
      next.add(path);
      if (!levels[path]) void load(path);
    }
    setOpen(next);
  }
  function file(f: BranchFile, depth: number, full = false) {
    return (
      <li key={f.id}>
        <button
          className={'virtual-branch-row' + (selected === f.id ? ' selected' : '')}
          style={{ paddingLeft: 10 + depth * 16 }}
          aria-current={selected === f.id || undefined}
          title={f.document_id ? 'Enlazado al documento registrado' : 'Sin documento registrado con la misma huella'}
          onClick={() => onSelect(f)}
        >
          <FileText size={15} aria-hidden="true" />
          <span className="virtual-branch-name">
            <MiddleText value={full ? f.virtual_path : f.name} />
          </span>
          {f.document_id ? (
            <Link2 size={14} className="virtual-branch-linked" aria-label="Enlazado al original" />
          ) : (
            <small className="muted">{(f.size / 1024).toFixed(1)} KB</small>
          )}
        </button>
      </li>
    );
  }
  function level(prefix: string, depth: number): ReactNode {
    const data = levels[prefix];
    if (!data) return loading.has(prefix) ? <li className="muted virtual-branch-status">Cargando…</li> : null;
    return (
      <>
        {data.folders.map((d) => (
          <li key={d.path}>
            <button
              className="virtual-branch-row folder"
              style={{ paddingLeft: 10 + depth * 16 }}
              aria-expanded={open.has(d.path)}
              onClick={() => toggle(d.path)}
            >
              {open.has(d.path) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              {open.has(d.path) ? <FolderOpen size={15} /> : <Folder size={15} />}
              <span className="virtual-branch-name">{d.name}</span>
              <small className="muted">{d.files}</small>
            </button>
            {open.has(d.path) && <ul>{level(d.path, depth + 1)}</ul>}
          </li>
        ))}
        {data.files.map((f) => file(f, depth))}
        {data.more && (
          <li className="muted virtual-branch-status" style={{ paddingLeft: 10 + depth * 16 }}>
            Se muestran los primeros 500 archivos de esta carpeta; usa la búsqueda para el resto.
          </li>
        )}
      </>
    );
  }

  const root = levels[''];
  return (
    <div className="virtual-branch">
      <div className="virtual-branch-toolbar">
        <div className="documents-search">
          <Search size={16} />
          <input
            aria-label="Buscar en la rama virtual"
            value={q}
            maxLength={120}
            placeholder="Buscar archivo o carpeta…"
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <button className="icon-button" aria-label="Actualizar rama virtual" onClick={() => setReload((n) => n + 1)}>
          <RefreshCw size={16} />
        </button>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          {error}
          <button onClick={() => setError('')}>Cerrar</button>
        </div>
      )}
      {found ? (
        found.files.length ? (
          <ul className="virtual-branch-tree">{found.files.map((f) => file(f, 0, true))}</ul>
        ) : (
          <p className="muted">Sin archivos que coincidan.</p>
        )
      ) : root && !root.folders.length && !root.files.length ? (
        <Empty icon={FolderOpen} title="Sin rama virtual todavía">
          Analiza la carpeta de la empresa con el agente local para construir el índice. Los originales no se mueven.
        </Empty>
      ) : (
        <ul className="virtual-branch-tree" aria-busy={loading.has('')}>
          {level('', 0)}
        </ul>
      )}
      <p className="documents-note muted">
        Orden virtual del último análisis de la carpeta. <Link2 size={12} /> indica un archivo enlazado al documento
        registrado con la misma huella SHA-256; su vista previa se abre aquí sin mostrar rutas del servidor.
      </p>
    </div>
  );
}
