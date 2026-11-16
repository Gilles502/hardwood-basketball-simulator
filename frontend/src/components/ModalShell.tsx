import React, { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';
import '../styles/ember-theme.css';
import './ModalShell.css';

interface ModalShellProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  /** Buttons shown in the header, left of the close button. */
  headerActions?: React.ReactNode;
  /** Full-width strip under the header (tabs, stepper). */
  headerExtra?: React.ReactNode;
  /** Footer content; the footer is only rendered when one of the two is given. */
  footerStart?: React.ReactNode;
  footerEnd?: React.ReactNode;
  maxWidth?: number;
  /** Fixed 85vh height, for dialogs whose content changes size (tabs, wizard steps). */
  tall?: boolean;
  /** When false, Escape and a click on the backdrop do not close the dialog (only the close button does). */
  dismissible?: boolean;
  /** When false, the header has no close button (a choice in the dialog must close it). */
  closable?: boolean;
  children: React.ReactNode;
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export const ModalShell: React.FC<ModalShellProps> = ({
  isOpen,
  onClose,
  title,
  subtitle,
  icon,
  headerActions,
  headerExtra,
  footerStart,
  footerEnd,
  maxWidth = 960,
  tall = false,
  dismissible = true,
  closable = true,
  children,
}) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  // Move focus into the dialog on open and give it back to the trigger on close.
  useEffect(() => {
    if (!isOpen) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    return () => previouslyFocused?.focus?.();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && dismissible) {
        onClose();
        return;
      }
      if (e.key !== 'Tab' || !dialogRef.current) return;
      const items = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || active === dialogRef.current)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, dismissible]);

  if (!isOpen) return null;

  const hasFooter = footerStart !== undefined || footerEnd !== undefined;

  return (
    <div className="ms-overlay ember-theme" onMouseDown={(e) => { if (dismissible && e.target === e.currentTarget) onClose(); }}>
      <div
        ref={dialogRef}
        className={`ms-dialog${tall ? ' ms-dialog-tall' : ''}`}
        style={{ maxWidth }}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="ms-header">
          <div className="ms-title-group">
            <div className="ms-icon">{icon}</div>
            <div style={{ minWidth: 0 }}>
              <h2 id={titleId} className="ms-title">{title}</h2>
              {subtitle && <p className="ms-subtitle">{subtitle}</p>}
            </div>
          </div>
          <div className="ms-header-actions">
            {headerActions}
            {closable && (
              <button className="ms-close" onClick={onClose} aria-label="Close">
                <X size={18} />
              </button>
            )}
          </div>
        </div>
        {headerExtra && <div className="ms-extra">{headerExtra}</div>}
        <div className="ms-body">{children}</div>
        {hasFooter && (
          <div className="ms-footer">
            <div>{footerStart}</div>
            <div className="ms-footer-end">{footerEnd}</div>
          </div>
        )}
      </div>
    </div>
  );
};
