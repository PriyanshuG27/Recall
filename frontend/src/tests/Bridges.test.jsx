import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Bridges from '../pages/Bridges';

describe.skip('Bridges Page Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders locked state when user has less than 50 items', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url) => {
      if (url.includes('/api/me')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ total_saves: 12 }) });
      }
      if (url.includes('/api/bridges')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({ ok: true });
    }));

    render(<Bridges />);

    await waitFor(() => {
      expect(screen.getByText(/COGNITIVE COMPATIBILITY/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/12 \/ 50/i)).toBeInTheDocument();
  });

  it('renders unlocked state and interacts with invite generation and bridge selection', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url, opts) => {
      if (url.includes('/api/me')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ total_saves: 50 }) });
      }
      if (url.includes('/api/bridges/invite')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ invite_code: 'CODE123' }) });
      }
      if (url.includes('/api/bridges/connect')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'connected' }) });
      }
      if (url.includes('/api/bridges/1')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            id: 1,
            friend_name: 'Bridge 1',
            compatibility_score: 95,
            synapses: [{ topic: 'AI', overlap: 0.9, item_a: { id: 10, title: 'Card A' }, item_b: { id: 20, title: 'Card B' } }]
          })
        });
      }
      if (url.includes('/api/bridges')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ id: 1, friend_name: 'Bridge 1' }]) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }));

    render(<Bridges />);

    await waitFor(() => {
      expect(screen.getByText(/NEURAL LINK GATEWAY/i)).toBeInTheDocument();
    });

    // Test Generate Invite Code
    const genBtn = screen.getByRole('button', { name: /Generate Invite Code/i });
    fireEvent.click(genBtn);

    await waitFor(() => {
      expect(screen.getByText('CODE123')).toBeInTheDocument();
    });

    // Test Connect Invite Code
    const input = screen.getByPlaceholderText(/MIND-XXXX-XXXX/i);
    fireEvent.change(input, { target: { value: 'FRIEND456' } });

    const connectBtn = screen.getByRole('button', { name: /CONNECT/i });
    fireEvent.click(connectBtn);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/bridges/connect', expect.anything());
    });

    // Select Bridge Card
    const decodeBtn = screen.getByText('DECODE NEURAL OVERLAP');
    fireEvent.click(decodeBtn);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/bridges/1');
    });
  });
});
