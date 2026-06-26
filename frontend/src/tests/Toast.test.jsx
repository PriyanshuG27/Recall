import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ToastProvider, useToast } from '../components/Toast';

function TestComponent() {
  const { addToast } = useToast();
  return (
    <div>
      <button onClick={() => addToast('Success message', 'success')}>Add Success Toast</button>
      <button onClick={() => addToast('Error message', 'error')}>Add Error Toast</button>
      <button onClick={() => addToast('Info message', 'info')}>Add Info Toast</button>
      <button onClick={() => addToast('Warning message', 'warning')}>Add Warning Toast</button>
    </div>
  );
}

describe('Toast Notification System', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('renders a success toast with correct role and content when triggered', () => {
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    );

    const button = screen.getByText('Add Success Toast');
    fireEvent.click(button);

    const toast = screen.getByRole('alert');
    expect(toast).toBeInTheDocument();
    expect(toast).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByText('Success message')).toBeInTheDocument();
    expect(screen.getByTestId('icon-CheckCircle')).toBeInTheDocument();
  });

  it('auto-dismisses a toast after 4 seconds', () => {
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Add Success Toast'));
    expect(screen.getByText('Success message')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(4000);
    });

    expect(screen.getByRole('alert')).toHaveClass('removing');

    act(() => {
      vi.advanceTimersByTime(200);
    });

    expect(screen.queryByText('Success message')).not.toBeInTheDocument();
  });

  it('evicts oldest toast when a 4th toast is added (limit to 3 concurrent)', () => {
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Add Success Toast'));
    fireEvent.click(screen.getByText('Add Error Toast'));
    fireEvent.click(screen.getByText('Add Info Toast'));
    fireEvent.click(screen.getByText('Add Warning Toast'));

    expect(screen.queryByText('Success message')).not.toBeInTheDocument();
    expect(screen.getByText('Error message')).toBeInTheDocument();
    expect(screen.getByText('Info message')).toBeInTheDocument();
    expect(screen.getByText('Warning message')).toBeInTheDocument();
  });
});
