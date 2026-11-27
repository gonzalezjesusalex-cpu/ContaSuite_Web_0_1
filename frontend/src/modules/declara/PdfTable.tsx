import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Undo2 } from 'lucide-react';
import { Badge, Empty } from '../../components/ui';
import { stitchButton } from '../../components/stitch';
import {
  FILTERS,
  MONTHS,
  STATUS_LABELS,
  STATUS_TONES,
  documentLabel,
  fileName,
  monthLabel,
  type PdfRecord,
} from './model';

type Column = 'file' | 'document' | 'period' | 'operation' | 'status' | 'final';
const COLUMNS: { id: Column; label: string }[] = [
  { id: 'file', label: 'Archivo actual' },
  { id: 'document', label: 'Documento' },
  { id: 'period', label: 'Periodo' },
  { id: 'operation', label: 'Nº operación' },
  { id: 'status', label: 'Estado' },
  { id: 'final', label: 'Nombre final' },
];

function sortKey(r: PdfRecord, column: Column): string | number {
  switch (column) {
    case 'file':
      return fileName(r.path).toLowerCase();
    case 'document':
      return documentLabel(r);
    case 'period':
      return (Number(r.year) || 0) * 100 + (r.month ? MONTHS.indexOf(r.month) + 1 : 0);
    case 'operation':
      return r.operation || '';
    case 'status':
      return STATUS_LABELS[r.status] || r.status;
    case 'final':
      return (r.expected_name || '').toLowerCase();
  }
}

/** Tabla de PDF con filtros por chip, orden por columna y desplazamiento horizontal en pantallas angostas. */
export default function PdfTable({
  records,
  generated,
  editable,
  busy,
  onOpen,
  onUndo,
}: {
  records: PdfRecord[];
  generated: boolean;
  editable: boolean;
  busy: boolean;
  onOpen: (index: number) => void;
  onUndo: (index: number) => void;
}) {
  const [filter, setFilter] = useState('todos');
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<{ column: Column; up: boolean }>({ column: 'period', up: true });
  const [page, setPage] = useState(0);
  const counts = useMemo(
    () => Object.fromEntries(FILTERS.map((f) => [f.id, records.filter(f.test).length])),
    [records],
  );
  const shown = useMemo(() => {
    const test = FILTERS.find((f) => f.id === filter)?.test || (() => true);
    const q = query.trim().toLowerCase();
    return records
      .filter(test)
      .filter(
        (r) =>
          !q ||
          `${r.path} ${r.expected_name || ''} ${r.rfc || ''} ${r.month || ''} ${r.operation || ''}`
            .toLowerCase()
            .includes(q),
      )
      .sort((a, b) => {
        const x = sortKey(a, sort.column);
        const y = sortKey(b, sort.column);
        const order = x < y ? -1 : x > y ? 1 : a.index - b.index;
        return sort.up ? order : -order;
      });
  }, [records, filter, query, sort]);
  const pages = Math.max(1, Math.ceil(shown.length / 50));
  const current = Math.min(page, pages - 1);
  return (
    <div className="declara-table-block">
      <div className="declara-chips" role="group" aria-label="Filtrar archivos">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            className={'declara-chip' + (filter === f.id ? ' active' : '')}
            aria-pressed={filter === f.id}
            onClick={() => {
              setFilter(f.id);
              setPage(0);
            }}
          >
            {f.label}
            <span className="declara-chip-count">{counts[f.id]}</span>
          </button>
        ))}
        <input
          className="declara-search"
          type="search"
          aria-label="Buscar archivo, RFC, mes u operación"
          placeholder="Buscar archivo, RFC, mes u operación…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
        />
      </div>
      <div className="declara-table-scroll" tabIndex={0} aria-label="Tabla de PDF">
        <table className="declara-table">
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th key={c.id} aria-sort={sort.column === c.id ? (sort.up ? 'ascending' : 'descending') : 'none'}>
                  <button
                    type="button"
                    onClick={() => setSort((s) => ({ column: c.id, up: s.column === c.id ? !s.up : true }))}
                  >
                    {c.label}
                    {sort.column === c.id &&
                      (sort.up ? <ArrowUp size={13} aria-hidden="true" /> : <ArrowDown size={13} aria-hidden="true" />)}
                  </button>
                </th>
              ))}
              <th>
                <span className="sr-only">Acción</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.slice(current * 50, current * 50 + 50).map((r) => (
              <tr key={r.index} onClick={() => onOpen(r.index)} className="declara-row">
                <td className="declara-file">
                  <strong>{fileName(r.path)}</strong>
                  {r.status !== 'RENOMBRAR' && r.status !== 'CORRECTO' && <small>{r.detail}</small>}
                </td>
                <td>
                  {documentLabel(r)}
                  {(r.is_resico || r.is_salarios) && (
                    <small>{[r.is_resico && 'RESICO', r.is_salarios && 'SALARIOS'].filter(Boolean).join(' · ')}</small>
                  )}
                </td>
                <td>
                  {r.month ? monthLabel(r.month) : 'Sin mes'} {r.year || ''}
                  {r.other_year && <Badge tone="amber">Ejercicio distinto</Badge>}
                </td>
                <td className="declara-mono">{r.operation || '—'}</td>
                <td>
                  <Badge tone={STATUS_TONES[r.status] || 'neutral'}>
                    {generated && r.status === 'RENOMBRAR' ? 'Renombrado' : STATUS_LABELS[r.status] || r.status}
                  </Badge>
                  {r.origin === 'manual' && r.status !== 'EXCLUIDO' && <Badge tone="blue">Manual</Badge>}
                  {r.status === 'RENOMBRAR' && !r.count_in_control && <small>No cuenta en el control</small>}
                </td>
                <td className="declara-final">{r.expected_name || '—'}</td>
                <td className="declara-row-actions" onClick={(e) => e.stopPropagation()}>
                  {editable && r.can_undo && (
                    <button
                      type="button"
                      className={stitchButton}
                      disabled={busy}
                      onClick={() => onUndo(r.index)}
                      title="Deshacer cambio manual"
                    >
                      <Undo2 size={15} />
                      <span className="sr-only">Deshacer cambio manual</span>
                    </button>
                  )}
                  <button type="button" className={stitchButton} onClick={() => onOpen(r.index)}>
                    {editable && !['CORRECTO', 'RENOMBRAR'].includes(r.status) ? 'Resolver' : 'Ver'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!shown.length && <Empty title="Sin archivos para mostrar">Cambia el filtro o la búsqueda.</Empty>}
      </div>
      {pages > 1 && (
        <div className="recopila-pagination">
          <button className={stitchButton} disabled={!current} onClick={() => setPage(current - 1)}>
            Anterior
          </button>
          <span>
            {current + 1} / {pages}
          </span>
          <button className={stitchButton} disabled={current + 1 >= pages} onClick={() => setPage(current + 1)}>
            Siguiente
          </button>
        </div>
      )}
    </div>
  );
}
