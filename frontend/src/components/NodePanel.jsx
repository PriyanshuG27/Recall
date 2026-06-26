import React, { useEffect, useRef } from 'react';
import { NodePanelSkeleton } from './Skeleton';
import FormattedText from './FormattedText';


export default function NodePanel({ selectedNode, loadingNodeDetail, onClose }) {
  const panelRef = useRef(null);

  useEffect(() => {
    if (!selectedNode || loadingNodeDetail) return;

    // Focus the first focusable element (the Close button) when panel opens
    const focusableElements = panelRef.current?.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (focusableElements && focusableElements.length > 0) {
      focusableElements[0].focus();
    }

    const handleKeyDown = (e) => {
      if (e.key !== 'Tab') return;

      const elements = panelRef.current?.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!elements || elements.length === 0) return;

      const firstElement = elements[0];
      const lastElement = elements[elements.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement.focus();
        }
      }
    };

    const handleClickOutside = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        if (e.target.closest('.constellation-node') || e.target.closest('.context-menu')) {
          return;
        }
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [selectedNode, loadingNodeDetail, onClose]);

  if (!selectedNode) return null;

  return (
    <div 
      ref={panelRef}
      className="node-panel glass-card"
      role="dialog"
      aria-modal="true"
      aria-labelledby="node-title-id"
    >
      {loadingNodeDetail ? (
        <NodePanelSkeleton />
      ) : (
        <>
          <h3 id="node-title-id" style={{ fontSize: '1.25rem', marginBottom: '0.75rem', color: 'var(--color-text)', marginTop: 0 }}>
            {selectedNode.title}
          </h3>
          <div style={{ marginTop: '1rem', marginBottom: '1.5rem', paddingRight: '0.25rem' }}>
            <FormattedText text={selectedNode.summary} />
          </div>
          <div style={{ marginTop: '1.5rem', display: 'flex', justifyContent: 'flex-end' }}>
            <button
              onClick={onClose}
              className="btn btn-secondary"
              style={{ padding: '0.4rem 0.8rem', fontSize: '0.8125rem', minHeight: '44px' }}
            >
              Close
            </button>
          </div>
        </>
      )}
    </div>
  );
}
