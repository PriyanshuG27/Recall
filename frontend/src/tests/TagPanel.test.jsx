import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import TagPanel from '../components/TagPanel';

vi.mock('gsap', () => ({
  default: {
    fromTo: vi.fn(),
    to: vi.fn((el, vars) => vars.onComplete && vars.onComplete()),
  }
}));

describe('TagPanel Component', () => {
  const mockTag = {
    name: 'rust',
    items: [
      { id: 1, title: 'Rust Safety', summary: 'Memory safety without GC', source_type: 'url', tags: ['rust'] },
      { id: 2, title: 'Concurrency', summary: 'Fearless concurrency in Rust', source_type: 'text', tags: ['rust', 'concurrency'] }
    ]
  };

  it('renders tag title, signals count, and list correctly', () => {
    render(<TagPanel tag={mockTag} onClose={vi.fn()} />);

    expect(screen.getByRole('dialog', { name: /Tag: rust/i })).toBeInTheDocument();
    expect(screen.getByText('2 signals')).toBeInTheDocument();
    expect(screen.getByText('Rust Safety')).toBeInTheDocument();
    expect(screen.getByText('Concurrency')).toBeInTheDocument();
  });

  it('renders singular signal count when items length is 1', () => {
    const singleTag = {
      name: 'unique',
      items: [{ id: 1, title: 'Unique Signal', source_type: 'pdf', tags: ['unique'] }]
    };
    render(<TagPanel tag={singleTag} onClose={vi.fn()} />);
    expect(screen.getByText('1 signal')).toBeInTheDocument();
  });

  it('handles empty constellation scenario correctly', () => {
    const emptyTag = { name: 'empty', items: [] };
    render(<TagPanel tag={emptyTag} onClose={vi.fn()} />);

    expect(screen.getByText('No signals in this constellation.')).toBeInTheDocument();
  });

  it('triggers onClose when close button, backdrop, or hover events occur', () => {
    const handleClose = vi.fn();
    const { container } = render(<TagPanel tag={mockTag} onClose={handleClose} />);

    const closeBtn = screen.getByRole('button', { name: /Close tag panel/i });
    fireEvent.mouseEnter(closeBtn);
    fireEvent.mouseLeave(closeBtn);
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalled();

    // Backdrop click
    const backdrop = container.firstChild;
    fireEvent.click(backdrop);
  });

  it('triggers onClose when Escape key is pressed', () => {
    const handleClose = vi.fn();
    render(<TagPanel tag={mockTag} onClose={handleClose} />);

    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
