import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ArchiveCard from '../components/ArchiveCard';

describe('ArchiveCard Component', () => {
  const mockItem = {
    id: 1,
    title: 'Test Title',
    summary: 'This is a test summary for testing the card components rendering.',
    source_type: 'url',
    created_at: new Date().toISOString(),
    tags: ['react', 'testing']
  };

  it('renders standard fields correctly', () => {
    render(<ArchiveCard item={mockItem} isActive={true} />);

    expect(screen.getByText('Test Title')).toBeInTheDocument();
    expect(screen.getByText(/This is a test summary/i)).toBeInTheDocument();
    expect(screen.getByText('url')).toBeInTheDocument();
    expect(screen.getByText('#react')).toBeInTheDocument();
    expect(screen.getByText('#testing')).toBeInTheDocument();
  });

  it('handles click event', () => {
    const handleClick = vi.fn();
    const { container } = render(
      <ArchiveCard item={mockItem} isActive={true} onClick={handleClick} />
    );

    const card = container.firstChild;
    fireEvent.click(card);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('handles mouse movements for 3D tilt effect when active', () => {
    const { container } = render(
      <ArchiveCard item={mockItem} isActive={true} />
    );
    const card = container.firstChild;

    // Dispatch mouse events
    fireEvent.mouseMove(card, { clientX: 100, clientY: 100 });
    expect(card.style.transform).toContain('perspective(1200px)');

    fireEvent.mouseLeave(card);
    expect(card.style.transform).toBe('perspective(1200px) rotateY(0deg) rotateX(0deg)');
  });
});
