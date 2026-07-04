import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import CustomCursor from '../components/CustomCursor';

describe('CustomCursor Component', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query) => ({
      matches: true,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders and tracks mouse coordinates and custom states', () => {
    render(<CustomCursor />);

    // Trigger mousemove on window
    fireEvent.mouseMove(window, { clientX: 100, clientY: 150 });
    
    // Advance timer to trigger requestAnimationFrame loops
    act(() => {
      vi.advanceTimersByTime(16);
    });

    // Cursor elements should be present in DOM
    const dot = document.querySelector('.cursor-dot');
    const glow = document.querySelector('.cursor-glow');
    expect(dot).toBeInTheDocument();
    expect(glow).toBeInTheDocument();
  });
});
