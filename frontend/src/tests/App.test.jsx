import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import App from '../App';
import { AuthProvider } from '../context/AuthContext';
import { ToastProvider } from '../components/Toast';

// Mock Web Audio API for tests
vi.stubGlobal('AudioContext', vi.fn().mockImplementation(() => ({
  createOscillator: () => ({
    type: 'sine',
    frequency: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
    connect: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
  }),
  createGain: () => ({
    gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
    connect: vi.fn(),
  }),
  destination: {},
  currentTime: 0,
})));

describe('App PWA and Session Tracking', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('increments atrium_visits on new session', () => {
    render(
      <ToastProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ToastProvider>
    );

    expect(sessionStorage.getItem('atrium_session_active')).toBe('true');
    expect(localStorage.getItem('atrium_visits')).toBe('1');
  });

  it('does not increment atrium_visits if session is active', () => {
    sessionStorage.setItem('atrium_session_active', 'true');
    localStorage.setItem('atrium_visits', '5');

    render(
      <ToastProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ToastProvider>
    );

    expect(localStorage.getItem('atrium_visits')).toBe('5');
  });

  it('renders splash loading state initially', () => {
    render(
      <ToastProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ToastProvider>
    );

    expect(screen.getByText(/Atrium/i)).toBeInTheDocument();
  });

  it('redirects unauthenticated users to /login', async () => {
    vi.stubGlobal('location', { pathname: '/archive', search: '', hash: '' });
    const replaceSpy = vi.spyOn(window.history, 'replaceState');

    vi.spyOn(window, 'fetch').mockImplementation(() =>
      Promise.resolve({ ok: false, status: 401 })
    );

    render(
      <ToastProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(replaceSpy).toHaveBeenCalledWith(expect.any(Object), '', '/login');
    });

    vi.unstubAllGlobals();
  });

  it('redirects authenticated users from /login to /dashboard', async () => {
    vi.stubGlobal('location', { pathname: '/login', search: '', hash: '' });
    const replaceSpy = vi.spyOn(window.history, 'replaceState');

    vi.spyOn(window, 'fetch').mockImplementation((url) => {
      if (url.includes('/me') || url.includes('/quizzes/stats')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ id: 1, chat_id: '12345', streak_count: 5, total_saves: 10 }),
        });
      }
      return Promise.resolve({ ok: false });
    });

    render(
      <ToastProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(replaceSpy).toHaveBeenCalledWith(expect.any(Object), '', '/archive');
    });

    vi.unstubAllGlobals();
  });
});
