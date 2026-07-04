import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import useMouseVelocity from '../hooks/useMouseVelocity';

describe('useMouseVelocity hook', () => {
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

  it('tracks mouse movement velocity and clamps it to normalised [0, 1]', () => {
    const { result } = renderHook(() => useMouseVelocity());

    // Initially 0 velocity
    expect(result.current.speed).toBe(0);

    // First move to establish position
    act(() => {
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: 10, clientY: 10 }));
    });

    // Move mouse and trigger calculations
    act(() => {
      currentTime += 10;
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: 20, clientY: 20 }));
    });

    // Tick the timers so requestAnimationFrame decay loop fires once, forcing a hook re-render
    act(() => {
      vi.advanceTimersByTime(16);
    });

    // Speed should be positive
    expect(result.current.speed).toBeGreaterThan(0);
    expect(result.current.vx).toBeGreaterThan(0);
    expect(result.current.vy).toBeGreaterThan(0);
    expect(result.current.normalised).toBeGreaterThan(0);
    expect(result.current.normalised).toBeLessThanOrEqual(1);
  });

  it('decays speed over time via requestAnimationFrame loop', () => {
    const { result } = renderHook(() => useMouseVelocity());

    act(() => {
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: 10, clientY: 10 }));
      currentTime += 10;
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: 50, clientY: 50 }));
    });

    act(() => {
      vi.advanceTimersByTime(16);
    });

    const speedAfterMove = result.current.speed;
    expect(speedAfterMove).toBeGreaterThan(0);

    // Advance time to allow exponential decay loop to tick further
    act(() => {
      vi.advanceTimersByTime(100);
    });

    expect(result.current.speed).toBeLessThan(speedAfterMove);
  });
});
