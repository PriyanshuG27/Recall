import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Settings from '../pages/Settings';
import { AuthProvider, useAuth } from '../context/AuthContext';
import { ToastProvider } from '../components/Toast';
import axios from 'axios';

vi.mock('axios', () => {
  const mockInstance = {
    create: vi.fn(() => mockInstance),
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() }
    }
  };
  return {
    default: mockInstance,
    ...mockInstance
  };
});

function SeedAuth({ user, children }) {
  const { login } = useAuth();
  React.useEffect(() => {
    if (user) login(user);
  }, [user]);
  return children;
}

describe('Settings Page Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    localStorage.clear();

    vi.spyOn(window, 'confirm').mockImplementation(() => true);
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-300);

    vi.spyOn(window, 'fetch').mockImplementation((url) => {
      if (url === '/auth/me') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ id: 42, chat_id: '99999' }),
        });
      }
      return Promise.resolve({ ok: false });
    });
  });

  it('renders stats, streak info, and updates timezone selection', async () => {
    axios.get.mockImplementation((url) => {
      if (url === '/api/me') {
        return Promise.resolve({
          data: {
            timezone_offset: 5.5,
            streak_count: 5,
            total_saves: 20,
            quizzes_answered: 3,
            drive_connected: false,
            digest_enabled: true
          }
        });
      }
      if (url === '/api/reminders') {
        return Promise.resolve({ data: [{ id: 1, message: 'Existing reminder', remind_at: '2026-07-10T10:00:00Z' }] });
      }
      return Promise.reject(new Error('not found'));
    });

    localStorage.setItem('timezone_explicitly_set', 'true');

    render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, username: 'testuser' }}>
            <Settings />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Profile & Settings')).toBeInTheDocument();
    });

    // Test timezone change
    const select = screen.getByLabelText(/Local Timezone Offset/i);
    fireEvent.change(select, { target: { value: '0' } });

    await waitFor(() => {
      expect(axios.patch).toHaveBeenCalled();
    });
  });

  it('handles exporting data backup', async () => {
    axios.get.mockImplementation((url) => {
      if (url === '/api/me') return Promise.resolve({ data: {} });
      if (url === '/api/reminders') return Promise.resolve({ data: [] });
      if (url === '/api/export') return Promise.resolve({ data: new Blob(['{}']) });
      return Promise.resolve({ data: {} });
    });

    localStorage.setItem('timezone_explicitly_set', 'true');

    render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, username: 'testuser' }}>
            <Settings />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Profile & Settings')).toBeInTheDocument();
    });

    const exportBtn = screen.getByRole('button', { name: /Export My Data \(JSON\)/i });
    fireEvent.click(exportBtn);

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/api/export', expect.anything());
    });
  });
});
