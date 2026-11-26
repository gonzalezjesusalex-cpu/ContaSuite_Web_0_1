import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { BarChart3, ClipboardCheck, FolderOpen, MoreHorizontal } from 'lucide-react';
import type { Company } from '../types';
import { dashboardUrl, dossierUrl } from '../companyNavigation';
import { confirmDiscard } from '../navigationGuard';

export type CompanyView = 'Expediente' | 'Dashboard' | 'Obligaciones';

/** Where each company view lives; the routes are the existing ones (Bloque 3). */
export function companyViewUrl(view: CompanyView, companyId: string, period: string, context?: URLSearchParams) {
  if (view === 'Expediente') return dossierUrl(companyId, 'Resumen', period, context);
  // Dashboard principal: Resumen o Obligaciones › Matriz del mes, filtrados a la empresa.
  return view === 'Dashboard'
    ? dashboardUrl('resumen', '', { period, company_id: companyId })
    : dashboardUrl('obligaciones', 'matriz', { period, company_id: companyId });
}

/** Compact company selector with the «include archived» switch inside it. */
export function CompanySwitcher({
  companies,
  companyId,
  onChange,
}: {
  companies: Company[];
  companyId: string;
  onChange: (id: string) => void;
}) {
  const [includeArchived, setIncludeArchived] = useState(false);
  const choices = companies
    .filter((x) => x.id === companyId || includeArchived || !x.archived)
    .sort((a, b) => a.name.localeCompare(b.name, 'es'));
  return (
    <div className="company-switcher">
      <label>
        <span>Empresa</span>
        <select aria-label="Cambiar empresa" value={companyId} onChange={(e) => onChange(e.target.value)}>
          {choices.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
              {x.archived ? ' · Archivada' : ''}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        role="switch"
        aria-checked={includeArchived}
        className={'switch' + (includeArchived ? ' on' : '')}
        onClick={() => setIncludeArchived((v) => !v)}
      >
        <span aria-hidden="true" />
        Incluir archivadas autorizadas
      </button>
    </div>
  );
}

/** Segmented selector Expediente / Dashboard de empresa / Control de obligaciones, the current one marked. */
export function CompanyViews({
  current,
  companyId,
  period,
  context,
}: {
  current: CompanyView;
  companyId: string;
  period: string;
  context?: URLSearchParams;
}) {
  const views: [CompanyView, string, ReactNode][] = [
    ['Expediente', 'Expediente', <FolderOpen size={16} key="e" />],
    ['Dashboard', 'Dashboard de empresa', <BarChart3 size={16} key="d" />],
    ['Obligaciones', 'Control de obligaciones', <ClipboardCheck size={16} key="o" />],
  ];
  return (
    <nav className="segmented" aria-label="Vistas de la empresa">
      {views.map(([view, label, icon]) => (
        <Link
          key={view}
          to={companyViewUrl(view, companyId, period, context)}
          aria-current={view === current ? 'page' : undefined}
          className={view === current ? 'active' : undefined}
          onClick={(e) => {
            if (view !== current && !confirmDiscard()) e.preventDefault();
          }}
        >
          {icon}
          <span>{label}</span>
        </Link>
      ))}
    </nav>
  );
}

/** «⋯» menu of secondary actions; closes with Escape, a click outside or after choosing. */
export function MoreMenu({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener('mousedown', outside);
    document.addEventListener('keydown', key);
    root.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    return () => {
      document.removeEventListener('mousedown', outside);
      document.removeEventListener('keydown', key);
    };
  }, [open]);
  return (
    <div className="more-menu" ref={root}>
      <button
        ref={button}
        type="button"
        className="btn icon-only"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <MoreHorizontal size={18} />
      </button>
      {open && (
        <div role="menu" className="more-menu-list" onClick={() => setOpen(false)}>
          {children}
        </div>
      )}
    </div>
  );
}
