import React from 'react';
import { render, screen, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from '../App';
import { AuthProvider, useAuth } from '../context/AuthContext';
import { ToastProvider } from '../components/Toast';

function SeedAuth({ user, children }) {
  const { login } = useAuth();
  React.useEffect(() => {
    if (user) login(user);
  }, [user]);
  return children;
}

describe('App PWA and Session Tracking', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();

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

  it('increments session visits on mount if new session', async () => {
    expect(localStorage.getItem('recall_visits')).toBeNull();

    render(
      <ToastProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ToastProvider>
    );

    expect(localStorage.getItem('recall_visits')).toBe('1');
    expect(sessionStorage.getItem('recall_session_active')).toBe('true');
  });

  it('triggers install toast on beforeinstallprompt event if visits >= 3', async () => {
    localStorage.setItem('recall_visits', '3');
    sessionStorage.setItem('recall_session_active', 'true');

    render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 1, chat_id: '12345' }}>
            <App />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Welcome to Recall')).toBeInTheDocument();
    });

    const userPromptChoice = Promise.resolve({ outcome: 'accepted' });
    const mockPromptEvent = {
      preventDefault: vi.fn(),
      prompt: vi.fn(),
      userChoice: userPromptChoice
    };

    act(() => {
      const event = new Event('beforeinstallprompt');
      Object.assign(event, mockPromptEvent);
      window.dispatchEvent(event);
    });

    await waitFor(() => {
      expect(screen.getByText('Add Recall to your homescreen?')).toBeInTheDocument();
    });

    const installBtn = screen.getByRole('button', { name: /Install/i });
    act(() => {
      installBtn.click();
    });

    await waitFor(() => {
      expect(mockPromptEvent.prompt).toHaveBeenCalled();
    });
  });
});
