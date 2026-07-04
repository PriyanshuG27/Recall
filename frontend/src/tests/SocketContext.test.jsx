import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SocketProvider, useGraphSocket } from '../context/SocketContext';
import { AuthProvider } from '../context/AuthContext';

vi.mock('../context/AuthContext', () => ({
  AuthProvider: ({ children }) => <>{children}</>,
  useAuth: () => ({ user: { id: 1, token: 'mock-token' } })
}));
import { ToastProvider } from '../components/Toast';

function TestConsumer() {
  const socket = useGraphSocket();
  return (
    <div>
      <span data-testid="status">{socket?.connectionStatus || 'none'}</span>
    </div>
  );
}

describe('SocketContext', () => {
  let mockWs;

  beforeEach(() => {
    vi.useFakeTimers();
    mockWs = {
      close: vi.fn(),
      send: vi.fn(),
      readyState: 1
    };
    vi.stubGlobal('WebSocket', vi.fn().mockImplementation(() => mockWs));
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url) => {
      if (url === '/auth/me') {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: 1 }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('provides socket connectionStatus', () => {
    render(
      <ToastProvider>
        <AuthProvider>
          <SocketProvider>
            <TestConsumer />
          </SocketProvider>
        </AuthProvider>
      </ToastProvider>
    );

    expect(screen.getByTestId('status')).toBeInTheDocument();
  });

  it('throws error if useGraphSocket is used outside provider', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<TestConsumer />)).toThrow('useGraphSocket must be used within a SocketProvider');
    consoleSpy.mockRestore();
  });
});
