import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SettingsPanel from '../components/SettingsPanel';
import { AuthProvider, useAuth } from '../context/AuthContext';
import { ToastProvider } from '../components/Toast';
import axios from 'axios';

vi.mock('axios', () => {
  const mockInstance = {
    create: vi.fn(() => mockInstance),
    get: vi.fn(),
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

describe('SettingsPanel Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    localStorage.clear();

    vi.spyOn(window, 'confirm').mockImplementation(() => true);

    // Mock local timezone offset to return -300 minutes (which is +5 hours)
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-300);

    // Mock auth API call
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

  it('renders settings panel when open and fetches settings data', async () => {
    axios.get.mockResolvedValue({
      data: {
        timezone_offset: 5,
        streak_count: 7,
        total_saves: 42,
        quizzes_answered: 12,
        drive_connected: true
      }
    });

    render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, chat_id: '99999' }}>
            <SettingsPanel isOpen={true} onClose={() => {}} />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    // Check loading indicator
    expect(screen.getByText('Loading preferences...')).toBeInTheDocument();

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/api/me');
      expect(screen.getByText('Settings')).toBeInTheDocument();
      expect(screen.getByText('🔥 7 days')).toBeInTheDocument();
      expect(screen.getByText('42')).toBeInTheDocument();
      expect(screen.getByText('12')).toBeInTheDocument();
      expect(screen.getByText('Connected')).toBeInTheDocument();
    });
  });

  it('updates timezone selection and sends PATCH request', async () => {
    axios.get.mockResolvedValue({
      data: {
        timezone_offset: 0,
        streak_count: 0,
        total_saves: 0,
        quizzes_answered: 0,
        drive_connected: false
      }
    });
    axios.patch.mockResolvedValue({});

    render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, chat_id: '99999' }}>
            <SettingsPanel isOpen={true} onClose={() => {}} />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByLabelText('Local Timezone Offset')).toBeInTheDocument();
    });

    const select = screen.getByLabelText('Local Timezone Offset');
    fireEvent.change(select, { target: { value: '5.5' } });

    await waitFor(() => {
      expect(axios.patch).toHaveBeenCalledWith('/api/me', { timezone_offset: 5.5 });
    });
  });

  it('disables delete button until DELETE is typed, then handles DELETE request', async () => {
    axios.get.mockResolvedValue({
      data: {
        timezone_offset: 0,
        streak_count: 0,
        total_saves: 0,
        quizzes_answered: 0,
        drive_connected: false
      }
    });
    axios.delete.mockResolvedValue({});

    render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, chat_id: '99999' }}>
            <SettingsPanel isOpen={true} onClose={() => {}} />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByPlaceholderText('DELETE')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('DELETE');
    const deleteBtn = screen.getByRole('button', { name: /Delete Account/i });

    expect(deleteBtn).toBeDisabled();

    // Type something other than DELETE
    fireEvent.change(input, { target: { value: 'NOTDELETE' } });
    expect(deleteBtn).toBeDisabled();

    // Type DELETE
    fireEvent.change(input, { target: { value: 'DELETE' } });
    expect(deleteBtn).not.toBeDisabled();

    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(axios.delete).toHaveBeenCalledWith('/api/me');
    });
  });

  it('automatically detects and updates timezone if not explicitly set', async () => {
    axios.get.mockResolvedValue({
      data: {
        timezone_offset: 0,
        streak_count: 0,
        total_saves: 0,
        quizzes_answered: 0,
        drive_connected: false
      }
    });
    axios.patch.mockResolvedValue({});

    render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, chat_id: '99999' }}>
            <SettingsPanel isOpen={true} onClose={() => {}} />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(axios.patch).toHaveBeenCalledWith('/api/me', { timezone_offset: 5 });
    });
  });
});
