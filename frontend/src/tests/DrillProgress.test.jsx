import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import DrillProgress from '../components/DrillProgress';

// Mock GSAP to prevent actual animation timers during tests
vi.mock('gsap', () => ({
  default: {
    to: vi.fn(),
    fromTo: vi.fn(),
  }
}));

describe('DrillProgress Component', () => {
  it('renders progress bar and counter correctly', () => {
    render(<DrillProgress current={3} total={10} />);

    expect(screen.getByText('3 / 10')).toBeInTheDocument();
  });

  it('handles empty progress smoothly', () => {
    render(<DrillProgress current={0} total={0} />);

    expect(screen.getByText('0 / 0')).toBeInTheDocument();
  });
});
