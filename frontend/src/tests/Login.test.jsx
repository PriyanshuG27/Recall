import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Login from '../pages/Login';
import { AuthProvider } from '../context/AuthContext';

describe('Login Component', () => {
  let fetchSpy;

  beforeEach(() => {
    vi.restoreAllMocks();
    fetchSpy = vi.spyOn(window, 'fetch').mockImplementation(() =>
      Promise.resolve({ ok: false })
    );
  });

  it('renders correctly', async () => {
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith('/auth/me');
    });

    expect(screen.getByText('Atrium')).toBeInTheDocument();
    
    await waitFor(() => {
      expect(screen.getByText(/Personal knowledge OS/i)).toBeInTheDocument();
    }, { timeout: 3000 });

    expect(screen.getByText('⚡ Go')).toBeInTheDocument();
  });

  it('performs developer bypass login successfully', async () => {
    const fetchSpy = vi.spyOn(window, 'fetch').mockImplementation((url) => {
      if (url.includes('/auth/telegram')) {
        return Promise.resolve({ ok: true });
      }
      if (url.includes('/auth/me')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: 12345, chat_id: '12345' }),
        });
      }
      return Promise.resolve({ ok: false });
    });

    render(
      <AuthProvider>
        <Login />
      </AuthProvider>
    );

    fireEvent.click(screen.getByText('⚡ Go'));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith('/auth/telegram?id=12345&mock=true');
      expect(fetchSpy).toHaveBeenCalledWith('/auth/me');
    });
  });

  it('displays error if developer bypass login fails', async () => {
    vi.spyOn(window, 'fetch').mockImplementation(() =>
      Promise.resolve({ ok: false })
    );

    render(
      <AuthProvider>
        <Login />
      </AuthProvider>
    );

    fireEvent.click(screen.getByText('⚡ Go'));

    await waitFor(() => {
      expect(screen.getByText('Bypass login failed.')).toBeInTheDocument();
    });
  });

  it('performs developer bypass login with custom chat ID if typed', async () => {
    const fetchSpy = vi.spyOn(window, 'fetch').mockImplementation((url) => {
      if (url.includes('/auth/telegram')) {
        return Promise.resolve({ ok: true });
      }
      if (url.includes('/auth/me')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: 98765, chat_id: '98765' }),
        });
      }
      return Promise.resolve({ ok: false });
    });

    render(
      <AuthProvider>
        <Login />
      </AuthProvider>
    );

    const input = screen.getByPlaceholderText(/123456789/i);
    fireEvent.change(input, { target: { value: '98765' } });
    fireEvent.click(screen.getByText('⚡ Go'));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith('/auth/telegram?id=98765&mock=true');
      expect(fetchSpy).toHaveBeenCalledWith('/auth/me');
    });
  });
});
