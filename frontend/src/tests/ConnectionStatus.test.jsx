import React from 'react';
import { render, screen, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import ConnectionStatus from '../components/ConnectionStatus';
import { useGraphSocket as useGraphSocketMock } from '../hooks/useGraphSocket';
import { SocketProvider, useGraphSocket as useGraphSocketReal } from '../context/SocketContext';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/Toast';

const STABLE_USER = { id: 'test-user', chat_id: '123456' };

// Mock useAuth
vi.mock('../context/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: STABLE_USER,
  })),
}));

// Mock useToast
vi.mock('../components/Toast', () => ({
  useToast: vi.fn(() => ({
    addToast: vi.fn(),
  })),
}));

describe('ConnectionStatus Component', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders green pulsing dot for connected state', () => {
    const now = Date.now();
    vi.mocked(useGraphSocketMock).mockReturnValue({
      connectionStatus: 'connected',
      lastSyncTime: now,
    });

    render(<ConnectionStatus />);
    
    const container = screen.getByTitle('Connected');
    expect(container).toBeInTheDocument();
    
    const dot = container.querySelector('.status-dot');
    expect(dot).toHaveClass('dot-connected');
    expect(screen.getByText(/Last updated: just now/)).toBeInTheDocument();
  });

  it('renders spinning amber dot for connecting state', () => {
    const now = Date.now();
    vi.mocked(useGraphSocketMock).mockReturnValue({
      connectionStatus: 'connecting',
      lastSyncTime: now,
    });

    render(<ConnectionStatus />);
    
    const container = screen.getByTitle('Connecting...');
    expect(container).toBeInTheDocument();
    
    const dot = container.querySelector('.status-dot');
    expect(dot).toHaveClass('dot-connecting');
  });

  it('renders static red dot and Reconnecting... tooltip for disconnected state', () => {
    const now = Date.now();
    vi.mocked(useGraphSocketMock).mockReturnValue({
      connectionStatus: 'disconnected',
      lastSyncTime: now,
    });

    render(<ConnectionStatus />);
    
    const container = screen.getByTitle('Reconnecting...');
    expect(container).toBeInTheDocument();
    
    const dot = container.querySelector('.status-dot');
    expect(dot).toHaveClass('dot-disconnected');
  });

  it('renders static red dot and Failed tooltip for failed state', () => {
    const now = Date.now();
    vi.mocked(useGraphSocketMock).mockReturnValue({
      connectionStatus: 'failed',
      lastSyncTime: now,
    });

    render(<ConnectionStatus />);
    
    const container = screen.getByTitle('Connection failed. Refresh to retry.');
    expect(container).toBeInTheDocument();
    
    const dot = container.querySelector('.status-dot');
    expect(dot).toHaveClass('dot-failed');
  });

  it('updates the last updated timestamp relative time text over time', () => {
    const now = Date.now();
    vi.mocked(useGraphSocketMock).mockReturnValue({
      connectionStatus: 'connected',
      lastSyncTime: now,
    });

    render(<ConnectionStatus />);
    expect(screen.getByText(/Last updated: just now/)).toBeInTheDocument();

    // Advance by 30 seconds
    const spy = vi.spyOn(Date, 'now').mockReturnValue(now + 30000);
    act(() => {
      vi.advanceTimersByTime(30000);
    });
    expect(screen.getByText(/Last updated: 30s ago/)).toBeInTheDocument();

    // Advance by another 30 seconds (total 60 seconds)
    spy.mockReturnValue(now + 60000);
    act(() => {
      vi.advanceTimersByTime(30000);
    });
    expect(screen.getByText(/Last updated: 1 minute ago/)).toBeInTheDocument();

    // Advance by another 60 seconds (total 120 seconds)
    spy.mockReturnValue(now + 120000);
    act(() => {
      vi.advanceTimersByTime(30000);
    });
    expect(screen.getByText(/Last updated: 2 minutes ago/)).toBeInTheDocument();

    spy.mockRestore();
  });
});

describe('SocketProvider Reconnect Logic', () => {
  let wsMockInstances = [];
  let originalWindowWebSocket;
  let originalGlobalWebSocket;

  beforeEach(() => {
    vi.useFakeTimers();
    originalWindowWebSocket = window.WebSocket;
    originalGlobalWebSocket = global.WebSocket;
    wsMockInstances = [];
    
    // Custom Mock WebSocket with static properties
    const MockWS = class MockWebSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;
      constructor(url) {
        this.url = url;
        this.readyState = 0; // CONNECTING
        wsMockInstances.push(this);
      }
      send = vi.fn();
      close = vi.fn();
    };
    window.WebSocket = MockWS;
    global.WebSocket = MockWS;
  });

  afterEach(() => {
    window.WebSocket = originalWindowWebSocket;
    global.WebSocket = originalGlobalWebSocket;
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('attempts reconnect with exponential backoff on close and fails after 5 attempts', async () => {
    const addToastMock = vi.fn();
    vi.mocked(useToast).mockReturnValue({ addToast: addToastMock });

    // Render SocketProvider with a dummy component using the hook
    let currentStatus = '';
    function TestComponent() {
      const { connectionStatus } = useGraphSocketReal();
      currentStatus = connectionStatus;
      return <div>Status: {connectionStatus}</div>;
    }

    render(
      <SocketProvider>
        <TestComponent />
      </SocketProvider>
    );

    // Initial state should trigger ws connect
    expect(wsMockInstances.length).toBe(1);
    const ws1 = wsMockInstances[0];

    // Simulate open
    act(() => {
      ws1.readyState = 1; // OPEN
      if (ws1.onopen) ws1.onopen();
    });
    expect(currentStatus).toBe('connected');

    // Simulate close to trigger reconnect 1 (1s backoff)
    act(() => {
      ws1.readyState = 3; // CLOSED
      if (ws1.onclose) ws1.onclose();
    });
    expect(currentStatus).toBe('disconnected');

    // Reconnect attempt 1 happens after 1000ms
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(wsMockInstances.length).toBe(2);
    const ws2 = wsMockInstances[1];
    
    // Reconnect attempt 2 (2s backoff)
    act(() => {
      ws2.readyState = 3;
      if (ws2.onclose) ws2.onclose();
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(wsMockInstances.length).toBe(3);
    const ws3 = wsMockInstances[2];

    // Reconnect attempt 3 (4s backoff)
    act(() => {
      ws3.readyState = 3;
      if (ws3.onclose) ws3.onclose();
    });
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    expect(wsMockInstances.length).toBe(4);
    const ws4 = wsMockInstances[3];

    // Reconnect attempt 4 (8s backoff)
    act(() => {
      ws4.readyState = 3;
      if (ws4.onclose) ws4.onclose();
    });
    act(() => {
      vi.advanceTimersByTime(8000);
    });
    expect(wsMockInstances.length).toBe(5);
    const ws5 = wsMockInstances[4];

    // Reconnect attempt 5 (16s backoff)
    act(() => {
      ws5.readyState = 3;
      if (ws5.onclose) ws5.onclose();
    });
    act(() => {
      vi.advanceTimersByTime(16000);
    });
    expect(wsMockInstances.length).toBe(6);
    const ws6 = wsMockInstances[5];

    // Close the 5th reconnect attempt -> transitions to failed and displays toast
    act(() => {
      ws6.readyState = 3;
      if (ws6.onclose) ws6.onclose();
    });
    
    expect(currentStatus).toBe('failed');
    expect(addToastMock).toHaveBeenCalledWith(
      'Real-time updates unavailable. Refresh to retry.',
      'error'
    );
  });
});
