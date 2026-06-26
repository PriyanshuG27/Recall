import React, { useEffect, useRef } from 'react';

export default function KeyboardShortcutsModal({ isOpen, onClose }) {
  const modalRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return;

    // Focus the first focusable element (the Close button) when modal opens
    const focusable = modalRef.current?.querySelectorAll('button, [tabindex="0"]');
    if (focusable && focusable.length > 0) {
      focusable[0].focus();
    }

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'Tab') {
        const elements = modalRef.current?.querySelectorAll('button, [tabindex="0"]');
        if (!elements || elements.length === 0) return;
        const first = elements[0];
        const last = elements[elements.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const shortcuts = [
    { key: '/', action: 'Focus search bar' },
    { key: 'Ctrl+K / Cmd+K', action: 'Focus search bar (alternative)' },
    { key: 'Escape', action: 'Close panel, modal, or clear search' },
    { key: 'G', action: 'Switch to Graph view' },
    { key: 'F', action: 'Switch to Feed view' },
    { key: '?', action: 'Show this keyboard shortcuts menu' }
  ];

  return (
    <div 
      className="modal-overlay" 
      onClick={handleOverlayClick}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.6)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000
      }}
    >
      <div 
        ref={modalRef}
        className="glass-card shortcuts-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-title"
        style={{
          padding: '2rem',
          borderRadius: '12px',
          maxWidth: '450px',
          width: '90%',
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)'
        }}
      >
        <h3 id="shortcuts-title" style={{ marginTop: 0, marginBottom: '1.5rem', color: 'var(--color-text)' }}>
          Keyboard Shortcuts
        </h3>
        
        <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: '1.5rem', color: 'var(--color-text)' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border-glass)' }}>
              <th style={{ textAlign: 'left', paddingBottom: '0.5rem', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>Shortcut</th>
              <th style={{ textAlign: 'left', paddingBottom: '0.5rem', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {shortcuts.map((s) => (
              <tr key={s.key} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <td style={{ padding: '0.75rem 0' }}>
                  <kbd style={{
                    background: 'rgba(255, 255, 255, 0.1)',
                    padding: '0.2rem 0.4rem',
                    borderRadius: '4px',
                    fontSize: '0.8125rem',
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--color-text)'
                  }}>{s.key}</kbd>
                </td>
                <td style={{ padding: '0.75rem 0', fontSize: '0.875rem', color: 'var(--color-text)' }}>{s.action}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button 
            onClick={onClose} 
            className="btn btn-primary"
            style={{ padding: '0.5rem 1.25rem', fontSize: '0.875rem', minHeight: '44px' }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
