import React from 'react';
import { render, screen, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import App from '../App';
import { AuthProvider } from '../context/AuthContext';
import { ToastProvider } from '../components/Toast';
import { setToastHandler, setUnauthorizedHandler } from '../api/client';

vi.mock('axios', () => {
  const mockInstance = {
    create: vi.fn(() => mockInstance),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: {
        use: vi.fn((fulfilled, rejected) => {
          globalThis.mockResponseRejectionHandler = rejected;
        }),
        eject: vi.fn()
      }
    }
  };
  return {
    default: mockInstance,
    ...mockInstance
  };
});

describe('Network and Offline Error Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default mocks for auth fetch requests
    vi.spyOn(window, 'fetch').mockImplementation((url) => {
      if (url === '/auth/me') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ id: 1, chat_id: '12345' }),
        });
      }
      if (url === '/api/quizzes/due') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([]),
        });
      }
      if (url.includes('/api/items')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ items: [], total: 0, pages: 1 }),
        });
      }
      return Promise.resolve({ ok: false });
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('triggers offline toast on offline event and removes it on online event', async () => {
    render(
      <ToastProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ToastProvider>
    );

    // Wait for the app to finish loading the Dashboard/Auth state
    await waitFor(() => {
      expect(screen.getByText('Welcome to Recall')).toBeInTheDocument();
    });

    // Trigger offline event
    act(() => {
      window.dispatchEvent(new Event('offline'));
    });

    // Verify offline toast is shown
    expect(screen.getByText("You're offline")).toBeInTheDocument();

    // Set up a listener for custom 'online-refetch' event
    const refetchSpy = vi.fn();
    window.addEventListener('online-refetch', refetchSpy);

    // Trigger online event
    act(() => {
      window.dispatchEvent(new Event('online'));
    });

    // Verify toast is removed
    expect(screen.queryByText("You're offline")).not.toBeInTheDocument();
    
    // Verify online-refetch was dispatched
    expect(refetchSpy).toHaveBeenCalled();
    window.removeEventListener('online-refetch', refetchSpy);
  });

  it('axios interceptor handles 401 unauthorized and triggers logout', async () => {
    const mockLogout = vi.fn();
    // Register custom handlers to test interceptor logic in isolation
    setUnauthorizedHandler(mockLogout);

    const error = {
      config: { url: '/api/search' },
      response: {
        status: 401
      }
    };

    // Invoke interceptor response error handler directly
    await expect(globalThis.mockResponseRejectionHandler(error)).rejects.toBeDefined();

    expect(mockLogout).toHaveBeenCalled();
  });

  it('axios interceptor ignores 401 unauthorized on auth endpoints', async () => {
    const mockLogout = vi.fn();
    setUnauthorizedHandler(mockLogout);

    const error = {
      config: { url: '/auth/me' },
      response: {
        status: 401
      }
    };

    await expect(globalThis.mockResponseRejectionHandler(error)).rejects.toBeDefined();

    expect(mockLogout).not.toHaveBeenCalled();
  });

  it('axios interceptor triggers correct toast for 429 Too Many Requests', async () => {
    const mockToast = vi.fn();
    setToastHandler(mockToast);

    const error = {
      config: { url: '/api/search' },
      response: {
        status: 429
      }
    };

    await expect(globalThis.mockResponseRejectionHandler(error)).rejects.toBeDefined();

    expect(mockToast).toHaveBeenCalledWith('Too many requests — please wait', 'warning');
  });

  it('axios interceptor triggers correct toast for 503 Service Unavailable', async () => {
    const mockToast = vi.fn();
    setToastHandler(mockToast);

    const error = {
      config: { url: '/api/search' },
      response: {
        status: 503
      }
    };

    await expect(globalThis.mockResponseRejectionHandler(error)).rejects.toBeDefined();

    expect(mockToast).toHaveBeenCalledWith('Server unavailable — retrying in 30 s', 'error');
  });

  it('axios interceptor triggers correct toast for network connection loss', async () => {
    const mockToast = vi.fn();
    setToastHandler(mockToast);

    const error = {
      // No response object indicates network error
      config: { url: '/api/search' }
    };

    await expect(globalThis.mockResponseRejectionHandler(error)).rejects.toBeDefined();

    expect(mockToast).toHaveBeenCalledWith('Connection lost — check your internet', 'error');
  });
});
