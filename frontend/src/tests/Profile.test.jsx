import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Profile from '../pages/Profile';

describe('Profile Page Component', () => {
  const mockProfile = {
    username: 'neon_hacker',
    created_at: '2026-01-01T00:00:00Z',
    cognitive_stats: {
      retention_rate: 85.5,
      daily_efficiency: 92.0,
      focus_index: 78.4,
      meta_score: 82.1,
      total_recalls: 412,
      active_nodes: 54,
      decay_half_life: 5.6
    },
    avatar_signature: 'BLVN',
    self_description: 'Cybernetic explorer of signals',
    pulse_score: 88
  };

  const mockMilestones = {
    node_count: 54,
    unlocked: ['pattern_report', 'mind_type']
  };

  const mockDetailed = {
    breadth: { score: 8.5, threshold: 7.0, desc: 'High breadth' },
    linkage: { score: 9.0, threshold: 8.0, desc: 'High linkage' },
    velocity: { score: 7.5, threshold: 6.0, desc: 'High velocity' },
    novelty: { score: 8.0, threshold: 7.0, desc: 'High novelty' }
  };

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url, opts) => {
      const urlStr = typeof url === 'string' ? url : (url.url || url.toString() || '');
      if (urlStr.includes('/api/user/profile/detailed')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockDetailed)
        });
      }
      if (urlStr.includes('/api/user/self-description')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) });
      }
      if (urlStr.includes('/api/user/profile')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockProfile) });
      }
      if (urlStr.includes('/api/user/milestones')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockMilestones) });
      }
      return Promise.resolve({ ok: true });
    }));
  });

  it('renders loading state initially and then shows profile data', async () => {
    render(<Profile />);

    await waitFor(() => {
      expect(screen.getByText('Cybernetic explorer of signals')).toBeInTheDocument();
    });

    expect(screen.getByText('Cognitive Explorer')).toBeInTheDocument();
  });

  it('interacts with detailed metrics generation', async () => {
    render(<Profile />);

    await waitFor(() => {
      expect(screen.getByText('Cognitive Explorer')).toBeInTheDocument();
    });

    const detailedBtn = screen.getByRole('button', { name: /INSPECT GRAPH METRICS/i });
    fireEvent.click(detailedBtn);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/user/profile/detailed', expect.anything());
    });
  });

  it('edits self description via Edit Direction', async () => {
    render(<Profile />);

    await waitFor(() => {
      expect(screen.getByText('Cybernetic explorer of signals')).toBeInTheDocument();
    });

    const editBtn = screen.getByRole('button', { name: /Edit Direction/i });
    fireEvent.click(editBtn);

    const textarea = screen.getByPlaceholderText(/What topics are you mostly interested/i);
    fireEvent.change(textarea, { target: { value: 'New updated bio' } });

    const saveBtn = screen.getByRole('button', { name: /^Save$/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/user/self-description', expect.anything());
    });
  });
});
