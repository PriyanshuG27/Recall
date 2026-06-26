import React from 'react';
import { render, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import useKeyboardShortcuts from '../hooks/useKeyboardShortcuts';
import KeyboardShortcutsModal from '../components/KeyboardShortcutsModal';

function TestComponent(props) {
  useKeyboardShortcuts(props);
  return (
    <div>
      <input type="text" data-testid="test-input" />
      <div data-testid="non-input">Hello</div>
    </div>
  );
}

describe('useKeyboardShortcuts Hook', () => {
  it('fires callbacks on matching key presses', () => {
    const onFocusSearch = vi.fn();
    const onClosePanel = vi.fn();
    const onSwitchToFeed = vi.fn();
    const onSwitchToGraph = vi.fn();
    const onShowShortcuts = vi.fn();

    render(
      <TestComponent
        onFocusSearch={onFocusSearch}
        onClosePanel={onClosePanel}
        onSwitchToFeed={onSwitchToFeed}
        onSwitchToGraph={onSwitchToGraph}
        onShowShortcuts={onShowShortcuts}
      />
    );

    // Press '/'
    fireEvent.keyDown(window, { key: '/' });
    expect(onFocusSearch).toHaveBeenCalledTimes(1);

    // Press 'Escape'
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClosePanel).toHaveBeenCalledTimes(1);

    // Press 'f'
    fireEvent.keyDown(window, { key: 'f' });
    expect(onSwitchToFeed).toHaveBeenCalledTimes(1);

    // Press 'g'
    fireEvent.keyDown(window, { key: 'g' });
    expect(onSwitchToGraph).toHaveBeenCalledTimes(1);

    // Press '?'
    fireEvent.keyDown(window, { key: '?' });
    expect(onShowShortcuts).toHaveBeenCalledTimes(1);

    // Press Ctrl+K
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
    expect(onFocusSearch).toHaveBeenCalledTimes(2);

    // Press Cmd+K (metaKey)
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    expect(onFocusSearch).toHaveBeenCalledTimes(3);
  });

  it('does not fire callbacks when inside input fields except Escape', () => {
    const onFocusSearch = vi.fn();
    const onClearSearch = vi.fn();
    const onSwitchToFeed = vi.fn();

    const { getByTestId } = render(
      <TestComponent
        onFocusSearch={onFocusSearch}
        onClearSearch={onClearSearch}
        onSwitchToFeed={onSwitchToFeed}
      />
    );

    const input = getByTestId('test-input');
    input.focus();

    // Try pressing '/'
    fireEvent.keyDown(input, { key: '/' });
    expect(onFocusSearch).not.toHaveBeenCalled();

    // Try pressing 'f'
    fireEvent.keyDown(input, { key: 'f' });
    expect(onSwitchToFeed).not.toHaveBeenCalled();

    // Press Escape inside input - should trigger onClearSearch
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(onClearSearch).toHaveBeenCalledTimes(1);
    expect(document.activeElement).not.toBe(input); // Should be blurred
  });
});

describe('KeyboardShortcutsModal Component', () => {
  it('renders modal when open and handles close action', () => {
    const onClose = vi.fn();
    const { getByText } = render(
      <KeyboardShortcutsModal isOpen={true} onClose={onClose} />
    );

    expect(getByText('Keyboard Shortcuts')).toBeInTheDocument();
    
    const closeBtn = getByText('Close');
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes modal when overlay is clicked', () => {
    const onClose = vi.fn();
    const { container } = render(
      <KeyboardShortcutsModal isOpen={true} onClose={onClose} />
    );

    const overlay = container.querySelector('.modal-overlay');
    fireEvent.click(overlay);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
