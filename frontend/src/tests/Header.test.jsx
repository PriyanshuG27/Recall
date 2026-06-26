import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Header from '../components/Header';
import { AuthProvider, useAuth } from '../context/AuthContext';

// Helper component to seed context
function SeedAuth({ user, children }) {
  const { login } = useAuth();
  React.useEffect(() => {
    if (user) login(user);
  }, [user]);
  return children;
}

describe('Header', () => {
  let currentUser = null;
  let fetchSpy;

  beforeEach(() => {
    vi.restoreAllMocks();
    currentUser = null;

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

    expect(screen.queryByText(/User /)).not.toBeInTheDocument();
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
      expect(screen.getByText('Recall')).toBeInTheDocument();
      expect(screen.getByText('User 99999')).toBeInTheDocument();
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
      expect(screen.getByText('User 99999')).toBeInTheDocument();
    });

    // Menu should be hidden initially
    expect(screen.queryByText(/Connect Google Drive/)).not.toBeInTheDocument();

    // Click trigger to open menu
    fireEvent.click(screen.getByText('User 99999'));
    expect(screen.getByText(/Connect Google Drive/)).toBeInTheDocument();

    // Click trigger again to close menu
    fireEvent.click(screen.getByText('User 99999'));
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
      expect(screen.getByText('User 99999')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('User 99999'));
    
    fireEvent.click(screen.getByText(/Connect Google Drive/));
    expect(windowOpenSpy).toHaveBeenCalledWith(
      '/auth/google',
      'Connect Google Drive',
      expect.stringContaining('width=500')
    );
  });

  it('disconnects Google Drive integration via DELETE /api/drive', async () => {
    currentUser = { id: 42, chat_id: '99999' };
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    render(
      <AuthProvider>
        <SeedAuth user={currentUser}>
          <Header />
        </SeedAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('User 99999')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('User 99999'));
    
    fireEvent.click(screen.getByText(/Disconnect Drive/));
    
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith('/api/drive', { method: 'DELETE' });
      expect(alertSpy).toHaveBeenCalledWith('Google Drive disconnected.');
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
      expect(screen.getByText('User 99999')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('User 99999'));
    
    fireEvent.click(screen.getByText(/Logout/));
    
    await waitFor(() => {
      expect(screen.queryByText('User 99999')).not.toBeInTheDocument();
    });
  });
});
