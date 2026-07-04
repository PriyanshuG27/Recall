import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Feed from '../pages/Feed';

describe('Feed Component', () => {
  const mockOnNodeClick = vi.fn();
  const mockOnViewInGraph = vi.fn();

  const mockTags = [
    { tag: 'react', count: 3 },
    { tag: 'vitest', count: 1 }
  ];

  const mockItemsPage1 = {
    items: [
      {
        id: 1,
        title: 'React Best Practices',
        summary: 'This is a summary about React best practices.',
        source_type: 'url',
        created_at: new Date(Date.now() - 3600000).toISOString(),
        tags: ['react', 'frontend']
      },
      {
        id: 2,
        title: 'Voice Note Idea',
        summary: 'Transcribed voice note details.',
        source_type: 'voice',
        created_at: new Date(Date.now() - 7200000).toISOString(),
        tags: ['voice']
      }
    ],
    pages: 2,
    page: 1,
    total: 3
  };

  let fetchSpy;

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();

    fetchSpy = vi.spyOn(window, 'fetch').mockImplementation(async (url) => {
      if (url.includes('/api/items')) {
        return {
          ok: true,
          status: 200,
          json: async () => mockItemsPage1
        };
      }
      if (url.includes('/api/tags')) {
        return {
          ok: true,
          status: 200,
          json: async () => mockTags
        };
      }
      return { ok: false, status: 404 };
    });
  });

  it('renders filter controls correctly', async () => {
    render(<Feed onNodeClick={mockOnNodeClick} onViewInGraph={mockOnViewInGraph} />);

    await waitFor(() => {
      expect(screen.getByText('Links')).toBeInTheDocument();
      expect(screen.getByText('Voice')).toBeInTheDocument();
      expect(screen.getByText('PDFs')).toBeInTheDocument();
      expect(screen.getByText('Images')).toBeInTheDocument();
      expect(screen.getByText('Text')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('#tag')).toBeInTheDocument();
    });
  });

  it('renders initial list of items', async () => {
    render(<Feed onNodeClick={mockOnNodeClick} onViewInGraph={mockOnViewInGraph} />);

    await waitFor(() => {
      expect(screen.getByText('React Best Practices')).toBeInTheDocument();
      expect(screen.getByText('Voice Note Idea')).toBeInTheDocument();
    });
  });

  it('filters items by source type on button click', async () => {
    render(<Feed onNodeClick={mockOnNodeClick} onViewInGraph={mockOnViewInGraph} />);

    await waitFor(() => {
      expect(screen.getByText('Links')).toBeInTheDocument();
    });

    const linksBtn = screen.getByText('Links');
    fireEvent.click(linksBtn);

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(expect.stringContaining('source_type=url'));
    });
  });

  it('handles tag input change and filter updates', async () => {
    render(<Feed onNodeClick={mockOnNodeClick} onViewInGraph={mockOnViewInGraph} />);

    await waitFor(() => {
      expect(screen.getByText('React Best Practices')).toBeInTheDocument();
    });

    const tagInput = screen.getByPlaceholderText('#tag');
    fireEvent.change(tagInput, { target: { value: 'react' } });

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(expect.stringContaining('tag=react'));
    });
  });

  it('triggers onNodeClick when item card is clicked', async () => {
    render(<Feed onNodeClick={mockOnNodeClick} onViewInGraph={mockOnViewInGraph} />);

    await waitFor(() => {
      expect(screen.getByText('React Best Practices')).toBeInTheDocument();
    });

    const card = screen.getByText('React Best Practices').closest('.feed-card');
    fireEvent.click(card);

    expect(mockOnNodeClick).toHaveBeenCalled();
  });
});
