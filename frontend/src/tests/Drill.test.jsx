import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import Drill from '../pages/Drill';

// Mock GSAP
vi.mock('gsap', () => ({
  default: {
    fromTo: vi.fn(),
    to: vi.fn(),
  }
}));

// Mock AudioEngine
vi.mock('../utils/AudioEngine', () => ({
  default: {
    playClick: vi.fn(),
    playReveal: vi.fn(),
    playSuccess: vi.fn(),
    playDrillActive: vi.fn(),
    stopDrillActive: vi.fn(),
  }
}));

describe('Drill Page Component', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(performance, 'now').mockImplementation(() => Date.now());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders loading state, boots, and lets user start drill', async () => {
    const mockStreakResponse = { streak_count: 5 };
    const mockQuizzesResponse = {
      quizzes: [
        { id: 1, question: 'React hook for side effects?', answer: 'useEffect', source_type: 'text' },
        { id: 2, question: 'React hook for state?', answer: 'useState', source_type: 'text' }
      ]
    };

    // Stub fetch requests
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url) => {
      if (url.includes('/api/me')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockStreakResponse) });
      }
      if (url.includes('/api/quizzes/due')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockQuizzesResponse) });
      }
      return Promise.resolve({ ok: true });
    }));

    render(<Drill />);

    // Resolve fetch promises
    await act(async () => {
      await Promise.resolve();
    });

    // Advance timers to trigger the typing animation useEffect and run it to completion
    act(() => {
      vi.advanceTimersByTime(3000);
    });

    // Check if boot phase text is printed
    expect(screen.getByText(/INITIALIZING SIGNAL RETRIEVAL/i)).toBeInTheDocument();

    // Click begin button
    const beginBtn = screen.getByRole('button', { name: /Begin Session/i });
    expect(beginBtn).toBeInTheDocument();
    
    act(() => {
      fireEvent.click(beginBtn);
    });

    // Now first card should be rendered
    expect(screen.getByText('React hook for side effects?')).toBeInTheDocument();
  });

  it('shows empty state when no cards are due', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url) => {
      if (url.includes('/api/me')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ streak_count: 0 }) });
      }
      if (url.includes('/api/quizzes/due')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ quizzes: [] }) });
      }
      return Promise.resolve({ ok: true });
    }));

    render(<Drill />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText(/NO TRANSMISSIONS DUE/i)).toBeInTheDocument();
  });
});
