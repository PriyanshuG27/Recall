import { useEffect } from 'react';

export default function useKeyboardShortcuts({
  onFocusSearch,
  onClosePanel,
  onClearSearch,
  onSwitchToFeed,
  onSwitchToGraph,
  onShowShortcuts
}) {
  useEffect(() => {
    const handleKeyDown = (e) => {
      const activeEl = document.activeElement;
      const isInput = 
        activeEl && 
        (activeEl.tagName === 'INPUT' || 
         activeEl.tagName === 'TEXTAREA' || 
         activeEl.isContentEditable);

      if (isInput) {
        if (e.key === 'Escape') {
          e.preventDefault();
          onClearSearch?.();
          activeEl.blur();
        }
        return;
      }

      // Check Ctrl+K or Cmd+K
      const isCmdK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k';
      if (isCmdK) {
        e.preventDefault();
        onFocusSearch?.();
        return;
      }

      switch (e.key) {
        case '/':
          e.preventDefault();
          onFocusSearch?.();
          break;
        case 'Escape':
          e.preventDefault();
          onClosePanel?.();
          break;
        case 'f':
        case 'F':
          e.preventDefault();
          onSwitchToFeed?.();
          break;
        case 'g':
        case 'G':
          e.preventDefault();
          onSwitchToGraph?.();
          break;
        case '?':
          e.preventDefault();
          onShowShortcuts?.();
          break;
        default:
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [
    onFocusSearch,
    onClosePanel,
    onClearSearch,
    onSwitchToFeed,
    onSwitchToGraph,
    onShowShortcuts
  ]);
}
