import React, { useEffect, useRef } from 'react';
import './Modal.css';

/**
 * Modal — replaces all alert() and window.confirm() usage.
 *
 * Props:
 *   isOpen          — controls visibility
 *   onClose         — called when user dismisses (backdrop click, Escape, Cancel)
 *   title           — dialog heading
 *   children        — body content
 *   confirmText     — label for the confirm button (optional)
 *   onConfirm       — callback for confirm button (optional)
 *   confirmVariant  — 'primary' | 'danger' (default: 'primary')
 *   cancelText      — label for cancel button (default: 'Cancel')
 *   showCancel      — whether to show the cancel button (default: true)
 */
function Modal({
  isOpen,
  onClose,
  title,
  children,
  confirmText,
  onConfirm,
  confirmVariant = 'primary',
  cancelText = 'Cancel',
  showCancel = true,
}) {
  const dialogRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      dialogRef.current?.focus();
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape' && isOpen) onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="presentation"
    >
      <div
        className="modal-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        ref={dialogRef}
        tabIndex={-1}
      >
        <div className="modal-header">
          <h2 id="modal-title" className="modal-title">
            {title}
          </h2>
          <button
            className="modal-close"
            onClick={onClose}
            aria-label="Close dialog"
          >
            ×
          </button>
        </div>

        <div className="modal-body">{children}</div>

        {(onConfirm || showCancel) && (
          <div className="modal-footer">
            {showCancel && (
              <button className="btn-secondary btn-sm" onClick={onClose}>
                {cancelText}
              </button>
            )}
            {onConfirm && (
              <button
                className={`btn-${confirmVariant} btn-sm`}
                onClick={() => {
                  onConfirm();
                  onClose();
                }}
              >
                {confirmText}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default Modal;
