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
    const dialog = ref.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog?.showModal();
    return () => {
      dialog?.close();
      // React has already removed the <dialog>, so the browser cannot return focus by itself:
      // give it back to the control that opened the dialog (keyboard users keep their place).
      if (opener?.isConnected && !document.querySelector('dialog[open]')) opener.focus();
    };
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
/** Long file names or paths: the start and the end stay visible, the full value in `title` and for screen
 *  readers (Bloque 6, B3). Never used for amounts, dates or identifiers the user compares. */
export function MiddleText({ value, max = 44 }: { value: string; max?: number }) {
  if (value.length <= max) return <span title={value}>{value}</span>;
  const head = Math.ceil((max - 1) * 0.6);
  const tail = max - 1 - head;
  return (
    <span title={value}>
      <span aria-hidden="true">{value.slice(0, head) + '…' + value.slice(-tail)}</span>
      <span className="sr-only">{value}</span>
    </span>
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
