import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import useScrollVelocity from '../hooks/useScrollVelocity';

describe('useScrollVelocity hook', () => {
  let currentTime = 1000;

  beforeEach(() => {
    currentTime = 1000;
    vi.useFakeTimers();
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(cb => setTimeout(cb, 16));
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(id => clearTimeout(id));
    vi.spyOn(performance, 'now').mockImplementation(() => currentTime);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('tracks scroll wheel event velocity and clamps it to normalised [0, 1]', () => {
    const { result } = renderHook(() => useScrollVelocity());

    // Initially 0 velocity
    expect(result.current).toBe(0);

    // Trigger wheel event
    act(() => {
      currentTime += 10;
      window.dispatchEvent(new WheelEvent('wheel', { deltaY: 100 }));
    });

    // Tick fake timers to trigger decay re-render
    act(() => {
      vi.advanceTimersByTime(16);
    });

    // Speed should be positive
    expect(result.current).toBeGreaterThan(0);
    expect(result.current).toBeLessThanOrEqual(1);
  });

  it('decays scroll velocity over time via decay loop', () => {
    const { result } = renderHook(() => useScrollVelocity());

    act(() => {
      currentTime += 10;
      window.dispatchEvent(new WheelEvent('wheel', { deltaY: 100 }));
    });

    act(() => {
      vi.advanceTimersByTime(16);
    });

    const valAfterScroll = result.current;
    expect(valAfterScroll).toBeGreaterThan(0);

    // Advance time to decay
    act(() => {
      vi.advanceTimersByTime(100);
    });

    expect(result.current).toBeLessThan(valAfterScroll);
  });
});
