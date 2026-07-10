import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Header from '../components/Header';
import { AuthProvider, useAuth } from '../context/AuthContext';
import axios from '../api/client';
import { useToast } from '../components/Toast';

// Mock axios client
vi.mock('../api/client', () => {
  const mockApiFetch = vi.fn().mockImplementation(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));
  return {
    default: {
      delete: vi.fn(),
      post: vi.fn(),
    },
    apiFetch: mockApiFetch,
  };
});

// Mock useToast
vi.mock('../components/Toast', () => {
  return {
    useToast: vi.fn(() => ({
      addToast: vi.fn(),
      removeToast: vi.fn(),
    })),
  };
});

// Helper component to seed context
function SeedAuth({ user, children }) {
  const { login } = useAuth();
  React.useEffect(() => {
    if (user) login(user);
  }, [user]);
  return children;
}

// Helper: open the profile dropdown
function openDropdown() {
  const trigger = screen.getByRole('button', { name: /Profile menu/i });
  fireEvent.click(trigger);
}

describe('Header', () => {
  let currentUser = null;
  let fetchSpy;

  beforeEach(() => {
    vi.restoreAllMocks();
    currentUser = null;

    vi.spyOn(window, 'confirm').mockImplementation(() => true);

    fetchSpy = vi.spyOn(window, 'fetch').mockImplementation(async (url, options) => {
      if (url === '/auth/me') {
        if (currentUser) {
          return {
            ok: true,
            status: 200,
            json: async () => currentUser,
          };
        } else {
          return {
            ok: false,
            status: 401,
            json: async () => ({ detail: 'Not authenticated' }),
          };
        }
      }
      if (url === '/auth/logout' && options?.method === 'POST') {
        currentUser = null;
        return {
          ok: true,
          status: 200,
          json: async () => ({ message: 'Logged out' }),
        };
      }
      if (url === '/api/drive' && options?.method === 'DELETE') {
        return {
          status: 204,
        };
      }
      if (url === '/api/quizzes/stats') {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            total: 10,
            due_today: 3,
            answered_all_time: 25,
            avg_ease_factor: 2.7,
            mastered: 4,
            mastered_definition: "ease_factor >= 2.5 AND interval_days >= 7",
            last_7_days: [
              { day: 'Mon', date: '2026-06-22', count: 2 },
              { day: 'Tue', date: '2026-06-23', count: 0 },
              { day: 'Wed', date: '2026-06-24', count: 5 },
              { day: 'Thu', date: '2026-06-25', count: 1 },
              { day: 'Fri', date: '2026-06-26', count: 0 },
              { day: 'Sat', date: '2026-06-27', count: 3 },
              { day: 'Sun', date: '2026-06-28', count: 4 }
            ]
          })
        };
      }
      return { ok: false, status: 404 };
    });
  });

  it('does not render profile trigger if user is guest', async () => {
    render(
      <AuthProvider>
        <Header />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith('/auth/me');
    });

    // No profile menu button when logged out
    expect(screen.queryByRole('button', { name: /Profile menu/i })).not.toBeInTheDocument();
  });

  it('renders logo and profile trigger if authenticated', async () => {
    currentUser = { id: 42, chat_id: '99999' };
    render(
      <AuthProvider>
        <SeedAuth user={currentUser}>
          <Header />
        </SeedAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      // Logo watermark is present
      expect(screen.getByText('Atrium')).toBeInTheDocument();
      // Profile trigger button is present
      expect(screen.getByRole('button', { name: /Profile menu/i })).toBeInTheDocument();
    });
  });

  it('toggles dropdown menu on click', async () => {
    currentUser = { id: 42, chat_id: '99999' };
    render(
      <AuthProvider>
        <SeedAuth user={currentUser}>
          <Header />
        </SeedAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Profile menu/i })).toBeInTheDocument();
    });

    // Menu should be hidden initially
    expect(screen.queryByText(/Connect Google Drive/)).not.toBeInTheDocument();

    // Click trigger to open menu
    openDropdown();
    expect(screen.getByText(/Connect Google Drive/)).toBeInTheDocument();

    // Click trigger again to close menu
    openDropdown();
    expect(screen.queryByText(/Connect Google Drive/)).not.toBeInTheDocument();
  });

  it('connects Google Drive via popup', async () => {
    currentUser = { id: 42, chat_id: '99999' };
    const windowOpenSpy = vi.spyOn(window, 'open').mockImplementation(() => ({}));
    
    render(
      <AuthProvider>
        <SeedAuth user={currentUser}>
          <Header />
        </SeedAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Profile menu/i })).toBeInTheDocument();
    });

    openDropdown();
    
    fireEvent.click(screen.getByText(/Connect Google Drive/));
    expect(windowOpenSpy).toHaveBeenCalledWith(
      '/auth/google',
      'atrium-drive-auth',
      expect.stringContaining('width=600')
    );
  });

  it('disconnects Google Drive integration via DELETE /api/drive', async () => {
    currentUser = { id: 42, chat_id: '99999', drive_connected: true };
    const addToastSpy = vi.fn();
    vi.mocked(useToast).mockReturnValue({
      addToast: addToastSpy,
      removeToast: vi.fn(),
    });
    axios.delete.mockResolvedValue({ status: 204 });

    render(
      <AuthProvider>
        <SeedAuth user={currentUser}>
          <Header />
        </SeedAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Profile menu/i })).toBeInTheDocument();
    });

    openDropdown();
    
    fireEvent.click(screen.getByText('Disconnect'));
    
    await waitFor(() => {
      expect(axios.delete).toHaveBeenCalledWith('/api/drive');
      expect(addToastSpy).toHaveBeenCalledWith('Google Drive disconnected successfully.', 'success');
    });
  });

  it('syncs Google Drive integration via POST /api/drive/sync', async () => {
    currentUser = { id: 42, chat_id: '99999', drive_connected: true };
    const addToastSpy = vi.fn();
    vi.mocked(useToast).mockReturnValue({
      addToast: addToastSpy,
      removeToast: vi.fn(),
    });
    axios.post.mockResolvedValue({ status: 202 });

    render(
      <AuthProvider>
        <SeedAuth user={currentUser}>
          <Header />
        </SeedAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Profile menu/i })).toBeInTheDocument();
    });

    openDropdown();
    
    fireEvent.click(screen.getByText('Sync Now'));
    
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith('/api/drive/sync');
      expect(addToastSpy).toHaveBeenCalledWith('Google Drive sync completed successfully!', 'success');
    });
  });

  it('triggers logout from context on menu click', async () => {
    currentUser = { id: 42, chat_id: '99999' };

    render(
      <AuthProvider>
        <SeedAuth user={currentUser}>
          <Header />
        </SeedAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Profile menu/i })).toBeInTheDocument();
    });

    openDropdown();
    
    fireEvent.click(screen.getByText(/Logout/));
    
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Profile menu/i })).not.toBeInTheDocument();
    });
  });

  it('renders quiz stats card and triggers onStatsClick on click', async () => {
    currentUser = { id: 42, chat_id: '99999' };
    const onStatsClickMock = vi.fn();

    render(
      <AuthProvider>
        <SeedAuth user={currentUser}>
          <Header onStatsClick={onStatsClickMock} />
        </SeedAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Due:')).toBeInTheDocument();
    });

    // Compact format: Due: 3 | Avg: 2.7
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('2.7')).toBeInTheDocument();

    const statsCard = screen.getByTitle('View detailed quiz performance history');
    fireEvent.click(statsCard);
    expect(onStatsClickMock).toHaveBeenCalled();
  });
});
