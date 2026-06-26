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
        created_at: new Date(Date.now() - 3600000).toISOString(), // 1 hour ago
        tags: ['react', 'frontend']
      },
      {
        id: 2,
        title: 'Voice Note Idea',
        summary: 'Transcribed voice note details.',
        source_type: 'voice',
        created_at: new Date(Date.now() - 7200000).toISOString(), // 2 hours ago
        tags: ['voice']
      }
    ],
    pages: 2,
    page: 1,
    total: 3
  };

  const mockItemsPage2 = {
    items: [
      {
        id: 3,
        title: 'Vite Setup',
        summary: 'A fast build tool configuration.',
        source_type: 'text',
        created_at: new Date(Date.now() - 86400000).toISOString(), // 1 day ago
        tags: ['vite']
      }
    ],
    pages: 2,
    page: 2,
    total: 3
  };

  let fetchSpy;

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();

    // Mock confirm dialog
    vi.spyOn(window, 'confirm').mockImplementation(() => true);

    fetchSpy = vi.spyOn(window, 'fetch').mockImplementation(async (url) => {
      if (url.includes('/api/tags')) {
        return {
          ok: true,
          status: 200,
          json: async () => mockTags
        };
      }
      if (url.includes('/api/items')) {
        const urlObj = new URL(url, 'http://localhost');
        const page = urlObj.searchParams.get('page');
        if (page === '2') {
          return {
            ok: true,
            status: 200,
            json: async () => mockItemsPage2
          };
        }
        return {
          ok: true,
          status: 200,
          json: async () => mockItemsPage1
        };
      }
      if (url.match(/\/api\/items\/\d+/) && url.includes('DELETE')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ message: 'Deleted' })
        };
      }
      return { ok: false, status: 404 };
    });
  });

  it('renders filter bar and datalist autocomplete options', async () => {
    render(<Feed onNodeClick={mockOnNodeClick} onViewInGraph={mockOnViewInGraph} />);

    await waitFor(() => {
      expect(screen.getByText('All')).toBeInTheDocument();
      expect(screen.getByText('Links')).toBeInTheDocument();
      expect(screen.getByText('Voice')).toBeInTheDocument();
      expect(screen.getByText('PDFs')).toBeInTheDocument();
      expect(screen.getByText('Images')).toBeInTheDocument();
      expect(screen.getByText('Text')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Search by tag...')).toBeInTheDocument();
    });

    // Check datalist option presence
    await waitFor(() => {
      const option = screen.getByText('3 saves');
      expect(option).toBeInTheDocument();
    });
  });

  it('renders initial list of items', async () => {
    render(<Feed onNodeClick={mockOnNodeClick} onViewInGraph={mockOnViewInGraph} />);

    await waitFor(() => {
      expect(screen.getByText('React Best Practices')).toBeInTheDocument();
      expect(screen.getByText('Voice Note Idea')).toBeInTheDocument();
      expect(screen.getByText('URL')).toBeInTheDocument();
      expect(screen.getByText('VOICE')).toBeInTheDocument();
      expect(screen.getByText('1h ago')).toBeInTheDocument();
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
      // It should refetch items with source_type=url query param
      expect(fetchSpy).toHaveBeenCalledWith(expect.stringContaining('source_type=url'));
    });
  });

  it('filters items by from_date and to_date range inputs', async () => {
    render(<Feed onNodeClick={mockOnNodeClick} onViewInGraph={mockOnViewInGraph} />);

    await waitFor(() => {
      expect(screen.getByLabelText('From Date')).toBeInTheDocument();
    });

    const fromDateInput = screen.getByLabelText('From Date');
    const toDateInput = screen.getByLabelText('To Date');

    fireEvent.change(fromDateInput, { target: { value: '2026-06-01' } });
    fireEvent.change(toDateInput, { target: { value: '2026-06-25' } });

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(expect.stringContaining('from_date=2026-06-01'));
      expect(fetchSpy).toHaveBeenCalledWith(expect.stringContaining('to_date=2026-06-25'));
    });
  });

  it('filters items by typing in tag autocomplete input', async () => {
    render(<Feed onNodeClick={mockOnNodeClick} onViewInGraph={mockOnViewInGraph} />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Search by tag...')).toBeInTheDocument();
    });

    const tagInput = screen.getByPlaceholderText('Search by tag...');
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

  it('handles item actions: delete item confirmation and API call', async () => {
    render(<Feed onNodeClick={mockOnNodeClick} onViewInGraph={mockOnViewInGraph} />);

    await waitFor(() => {
      expect(screen.getByText('React Best Practices')).toBeInTheDocument();
    });

    const actionTriggers = screen.getAllByLabelText('Item Actions');
    fireEvent.click(actionTriggers[0]); // Open dropdown menu for first card

    await waitFor(() => {
      expect(screen.getByText('Delete')).toBeInTheDocument();
    });

    const deleteBtn = screen.getByText('Delete');
    fireEvent.click(deleteBtn);

    // Verify window.confirm was shown and DELETE API was called
    await waitFor(() => {
      expect(window.confirm).toHaveBeenCalled();
      expect(fetchSpy).toHaveBeenCalledWith(expect.stringContaining('/api/items/1'), { method: 'DELETE' });
      // React Best Practices should be deleted/removed from list
      expect(screen.queryByText('React Best Practices')).not.toBeInTheDocument();
    });
  });

  it('handles item actions: view in graph call', async () => {
    render(<Feed onNodeClick={mockOnNodeClick} onViewInGraph={mockOnViewInGraph} />);

    await waitFor(() => {
      expect(screen.getByText('React Best Practices')).toBeInTheDocument();
    });

    const actionTriggers = screen.getAllByLabelText('Item Actions');
    fireEvent.click(actionTriggers[0]);

    await waitFor(() => {
      expect(screen.getByText('View in Graph')).toBeInTheDocument();
    });

    const viewInGraphBtn = screen.getByText('View in Graph');
    fireEvent.click(viewInGraphBtn);

    expect(mockOnViewInGraph).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
  });

  it('calls search API and displays results when searchQuery is provided', async () => {
    const searchMockResults = {
      query: 'neural networks',
      answer: null,
      sources: [
        {
          id: 10,
          title: 'Neural Networks Basics',
          summary: 'Intro to neural networks and deep learning.',
          relevance: 0.95,
          source_type: 'url',
          tags: ['ai'],
          created_at: new Date().toISOString()
        }
      ]
    };

    fetchSpy.mockImplementation(async (url, options) => {
      if (url.includes('/api/search')) {
        return {
          ok: true,
          status: 200,
          json: async () => searchMockResults
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

    render(
      <Feed 
        onNodeClick={mockOnNodeClick} 
        onViewInGraph={mockOnViewInGraph} 
        searchQuery="neural networks" 
      />
    );

    // Verify it fetched from the search API
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith('/api/search', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ query: 'neural networks', limit: 50, rag: false })
      }));
    });

    // Verify it renders the search result card
    await waitFor(() => {
      expect(screen.getByText('Neural Networks Basics')).toBeInTheDocument();
      expect(screen.getByText('Intro to neural networks and deep learning.')).toBeInTheDocument();
    });
  });

  it('renders search empty state when active query returns no matched items', async () => {
    fetchSpy.mockImplementation(async (url) => {
      if (url.includes('/api/search')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            query: 'unknown concept',
            answer: null,
            sources: []
          })
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

    render(
      <Feed 
        onNodeClick={mockOnNodeClick} 
        onViewInGraph={mockOnViewInGraph} 
        searchQuery="unknown concept" 
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('empty-state-search')).toBeInTheDocument();
      expect(screen.getByText('Try a different search term or check for typos.')).toBeInTheDocument();
    });
  });
});
