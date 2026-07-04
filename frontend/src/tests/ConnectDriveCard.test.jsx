import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ConnectDriveCard from '../components/ConnectDriveCard';
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

describe('ConnectDriveCard Component', () => {
  let openSpy;

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    localStorage.clear();

    openSpy = vi.spyOn(window, 'open').mockImplementation(() => ({
      closed: false,
      close: vi.fn()
    }));

    vi.spyOn(window, 'confirm').mockImplementation(() => true);

    vi.spyOn(window, 'fetch').mockImplementation((url) => {
      if (url === '/auth/me') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ id: 42, chat_id: '99999', drive_connected: true }),
        });
      }
      return Promise.resolve({ ok: false });
    });
  });

  it('renders disconnected state and handles popup connect', async () => {
    render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, drive_connected: false }}>
            <ConnectDriveCard />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    const connectBtn = screen.getByRole('button', { name: /Connect Google Drive/i });
    fireEvent.click(connectBtn);

    expect(openSpy).toHaveBeenCalledWith('/auth/google', 'recall-drive-auth', expect.any(String));
  });

  it('handles sync and disconnect error branches in connected state', async () => {
    axios.post.mockRejectedValue(new Error('Sync error'));
    axios.delete.mockRejectedValue(new Error('Disconnect error'));

    render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, drive_connected: true }}>
            <ConnectDriveCard />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/Google Drive connected/i)).toBeInTheDocument();
    });

    const syncBtn = screen.getByRole('button', { name: /Sync Now/i });
    fireEvent.click(syncBtn);

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith('/api/drive/sync');
    });

    const disconnectBtn = screen.getByRole('button', { name: /Disconnect/i });
    fireEvent.click(disconnectBtn);

    await waitFor(() => {
      expect(axios.delete).toHaveBeenCalledWith('/api/drive');
    });
  });
});
