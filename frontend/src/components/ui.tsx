import { confirmDiscard } from '../dirtyForms';
import { useEffect, useRef, useId, type ReactNode } from 'react';
import { X, Building2 } from 'lucide-react';
import { OriginalIcon } from './OriginalIcon';
export function Logo({ large = false, sidebar = false }: { large?: boolean; sidebar?: boolean }) {
  return (
    <div className={'brand-icon original-brand ' + (large ? 'large' : '')}>
      <OriginalIcon name="suite" size={large ? 104 : 40} sidebar={sidebar} label="ContaSuite" />
    </div>
  );
}
export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) {
  return <span className={'badge ' + tone}>{children}</span>;
}
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <Building2 size={32} />
      <h3>{title}</h3>
      <div className="empty-description">{children || 'Los registros aparecerán aquí cuando los agregues.'}</div>
    </div>
  );
}
export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const titleId = useId();
  const ref = useRef<HTMLDialogElement>(null);
  const leaving = useRef(false);
  const keeping = useRef(false);
  const close = () => {
    if (confirmDiscard()) {
      leaving.current = true;
      onClose();
      return;
    }
    // The user kept their changes. Chromium may still close the <dialog> after an Escape whose
    // cancel event was prevented (close-watcher rules), leaving it mounted but invisible: reopen it.
    keeping.current = true;
    setTimeout(() => {
      const dialog = ref.current;
      if (dialog?.isConnected && !dialog.open) dialog.showModal();
      else keeping.current = false;
    });
  };
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      aria-labelledby={titleId}
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClose={() => {
        // Closed by the browser: either the pending close after "keep" above, or a close request that
        // never went through the guard (non-cancelable Escape). Only the latter needs to ask.
        if (keeping.current) keeping.current = false;
        else if (!leaving.current) close();
      }}
      onClick={(e) => {
        if (e.target === ref.current) close();
      }}
    >
      <div className="modal-head">
        <h2 id={titleId}>{title}</h2>
        <button className="icon-button" aria-label="Cerrar" onClick={close}>
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Heading({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1 tabIndex={-1}>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="actions">{actions}</div>
    </div>
  );
}
export function Field({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <label className={wide ? 'field wide' : 'field'}>
      <span>{label}</span>
      {children}
    </label>
  );
}
export function Kpi({
  label,
  value,
  detail,
  tone = 'neutral',
}: {
  label: string;
  value: ReactNode;
  detail: string;
  tone?: string;
}) {
  return (
    <div className={'card kpi ' + tone}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
