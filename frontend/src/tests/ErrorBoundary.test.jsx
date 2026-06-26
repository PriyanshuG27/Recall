import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest';
import ErrorBoundary from '../components/ErrorBoundary';

function FaultyChild({ shouldThrow }) {
  if (shouldThrow) {
    throw new Error('Test rendering crash');
  }
  return <div>Everything is fine</div>;
}

describe('ErrorBoundary', () => {
  const originalLocation = window.location;

  beforeAll(() => {
    // Mock console.error to prevent mock error messages from cluttering log outputs
    vi.spyOn(console, 'error').mockImplementation(() => {});
    
    // Redefine window.location in test env to mock reload
    delete window.location;
    window.location = { reload: vi.fn() };
  });

  afterAll(() => {
    window.location = originalLocation;
    console.error.mockRestore();
  });

  it('renders children when no error is thrown', () => {
    render(
      <ErrorBoundary>
        <FaultyChild shouldThrow={false} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Everything is fine')).toBeInTheDocument();
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
  });

  it('catches rendering errors and displays fallback UI', () => {
    render(
      <ErrorBoundary>
        <FaultyChild shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.queryByText('Everything is fine')).not.toBeInTheDocument();
    expect(console.error).toHaveBeenCalled();
  });

  it('triggers page reload when reload button is clicked', () => {
    render(
      <ErrorBoundary>
        <FaultyChild shouldThrow={true} />
      </ErrorBoundary>
    );

    const reloadBtn = screen.getByText('Reload');
    fireEvent.click(reloadBtn);

    expect(window.location.reload).toHaveBeenCalled();
  });
});
