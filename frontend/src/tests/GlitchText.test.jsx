import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import GlitchText from '../components/GlitchText';

describe('GlitchText Component', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(performance, 'now').mockImplementation(() => Date.now());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders children text by default', () => {
    render(<GlitchText>Test Content</GlitchText>);
    expect(screen.getByText('Test Content')).toBeInTheDocument();
  });

  it('immediately glitches text when trigger is true', () => {
    const { container } = render(<GlitchText trigger={true}>Hello</GlitchText>);
    
    // The text should not be "Hello" anymore; it should be glitched (different characters)
    const textNode = container.querySelector('span');
    expect(textNode.textContent).not.toBe('Hello');
    expect(textNode.textContent.length).toBe(5);
  });

  it('resolves back to original children after duration', () => {
    const { container } = render(<GlitchText trigger={true} duration={150}>Hello</GlitchText>);
    
    act(() => {
      vi.advanceTimersByTime(200);
    });

    const textNode = container.querySelector('span');
    expect(textNode.textContent).toBe('Hello');
  });
});
