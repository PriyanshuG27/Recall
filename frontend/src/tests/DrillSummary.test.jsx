import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import DrillSummary from '../components/DrillSummary';

// Mock GSAP to avoid animations running during tests
vi.mock('gsap', () => ({
  default: {
    fromTo: vi.fn(),
  }
}));

// Mock AudioEngine
vi.mock('../utils/AudioEngine', () => ({
  default: {
    playClick: vi.fn(),
  }
}));

describe('DrillSummary Component', () => {
  let currentTime = 1000;

  beforeEach(() => {
    currentTime = 1000;
    vi.useFakeTimers();
    vi.spyOn(performance, 'now').mockImplementation(() => currentTime);
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(cb => {
      return setTimeout(() => cb(performance.now()), 16);
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  const mockScores = { locked: 4, shaky: 2, miss: 1 };

  it('renders summary values and animates them', async () => {
    render(
      <DrillSummary
        scores={mockScores}
        total={7}
        nextReviewAt={new Date(Date.now() + 86400000).toISOString()}
        streak={3}
        onNavigate={() => {}}
      />
    );

    // Speed up requestAnimationFrame count-up loops by advancing time and performance.now
    act(() => {
      currentTime += 1000;
      vi.advanceTimersByTime(1000);
    });

    expect(screen.getByText('4 of 7 locked in.')).toBeInTheDocument();
    expect(screen.getByText('Day 3 streak')).toBeInTheDocument();
    expect(screen.getByText('back in 1 day', { exact: false })).toBeInTheDocument();
  });

  it('triggers navigation callback on buttons click', () => {
    const handleNavigate = vi.fn();
    render(
      <DrillSummary
        scores={mockScores}
        total={7}
        nextReviewAt={null}
        streak={0}
        onNavigate={handleNavigate}
      />
    );

    const browseBtn = screen.getByRole('button', { name: /Browse Archive/i });
    fireEvent.click(browseBtn);
    expect(handleNavigate).toHaveBeenCalledWith('archive');

    const exploreBtn = screen.getByRole('button', { name: /Explore Map/i });
    fireEvent.click(exploreBtn);
    expect(handleNavigate).toHaveBeenCalledWith('map');
  });
});
