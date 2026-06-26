import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Dashboard from '../pages/Dashboard';
import { AuthProvider, useAuth } from '../context/AuthContext';
import axios from 'axios';

vi.mock('axios', () => {
  const mockInstance = {
    create: vi.fn(() => mockInstance),
    post: vi.fn().mockResolvedValue({
      data: {
        sources: [
          { id: 1, title: 'Machine Learning', summary: 'AI and neural networks' },
          { id: 3, title: 'FastAPI Guide', summary: 'High-performance web API framework' }
        ]
      }
    }),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() }
    }
  };
  return {
    default: mockInstance,
    ...mockInstance
  };
});

function SeedAuth({ user, children }) {
  const { login } = useAuth();
  React.useEffect(() => {
    if (user) login(user);
  }, [user]);
  return children;
}

describe('Dashboard Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();

    axios.post.mockResolvedValue({
      data: {
        sources: [
          { id: 1, title: 'Machine Learning', summary: 'AI and neural networks' },
          { id: 3, title: 'FastAPI Guide', summary: 'High-performance web API framework' }
        ]
      }
    });

    vi.spyOn(window, 'fetch').mockImplementation((url) => {
      if (url === '/auth/me') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ id: 42, chat_id: '99999' }),
        });
      }
      if (url === '/api/quizzes/due') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([
            { id: 1, question: 'React hook?' }
          ]),
        });
      }
      if (url.includes('/api/items')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            items: [
              { id: 1, title: 'Machine Learning', summary: 'AI and neural networks', source_type: 'url', source_url: 'https://example.com/ml', tags: ['ml'], created_at: '2026-06-26' },
              { id: 2, title: 'Transformers', summary: 'Attention is all you need', source_type: 'url', source_url: 'https://example.com/transformers', tags: ['transformers'], created_at: '2026-06-26' }
            ],
            total: 2,
            pages: 1
          }),
        });
      }
      if (url.includes('/api/graph')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            nodes: [
              { id: 1, title: 'Machine Learning', source_type: 'url', created_at: '2026-06-26', is_hub: true },
              { id: 2, title: 'Transformers', source_type: 'url', created_at: '2026-06-26', is_hub: false }
            ],
            edges: [
              { source: 1, target: 2, weight: 0.85 }
            ],
            hubs: [
              { id: 1, label: 'AI Guides', member_ids: [1] }
            ]
          }),
        });
      }
      return Promise.resolve({ ok: false });
    });
  });

  it('renders dashboard with user chat ID and animation node texts', async () => {
    render(
      <AuthProvider>
        <SeedAuth user={{ id: 42, chat_id: '99999' }}>
          <Dashboard />
        </SeedAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Welcome to Recall')).toBeInTheDocument();
      expect(screen.getByText('99999')).toBeInTheDocument();
      expect(screen.getByText(/Your knowledge constellation is ready/)).toBeInTheDocument();
    });
  });

  it('handles search debounce, axios search call, and node dimming', async () => {
    render(
      <AuthProvider>
        <SeedAuth user={{ id: 42, chat_id: '99999' }}>
          <Dashboard />
        </SeedAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Search your brain...')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Search your brain...');
    fireEvent.change(searchInput, { target: { value: 'neural networks' } });

    // Wait for the 300ms debounce
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith('/api/search', { query: 'neural networks', rag: false });
    });

    // Node 1 (Machine Learning) and Node 3 (FastAPI Guide) match the search result list
    // Verify Node 1 is highlighted (opacity 1) and Node 2 (Transformers) is dimmed (opacity 0.1)
    await waitFor(() => {
      const mlNode = screen.getByText('Machine Learning').closest('.constellation-node');
      const tfNode = screen.getByText('Transformers').closest('.constellation-node');

      expect(mlNode.style.opacity).toBe('1');
      expect(tfNode.style.opacity).toBe('0.1');
    });

    // Clear search
    const clearBtn = screen.getByText('Clear');
    fireEvent.click(clearBtn);

    await waitFor(() => {
      const mlNode = screen.getByText('Machine Learning').closest('.constellation-node');
      const tfNode = screen.getByText('Transformers').closest('.constellation-node');

      expect(mlNode.style.opacity).toBe('1');
      expect(tfNode.style.opacity).toBe('1');
    });
  });

  it('shows side detail panel when node is clicked', async () => {
    render(
      <AuthProvider>
        <SeedAuth user={{ id: 42, chat_id: '99999' }}>
          <Dashboard />
        </SeedAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Machine Learning')).toBeInTheDocument();
    });

    const mlNode = screen.getByText('Machine Learning').closest('.constellation-node');
    fireEvent.click(mlNode);

    // Verify detail panel opens
    await waitFor(() => {
      expect(screen.getByText('AI and neural networks')).toBeInTheDocument();
    });

    const closeBtn = screen.getByText('Close');
    fireEvent.click(closeBtn);

    // Verify detail panel closes
    expect(screen.queryByText('AI and neural networks')).not.toBeInTheDocument();
  });

  it('closes side detail panel when clicking outside', async () => {
    render(
      <AuthProvider>
        <SeedAuth user={{ id: 42, chat_id: '99999' }}>
          <Dashboard />
        </SeedAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Machine Learning')).toBeInTheDocument();
    });

    const mlNode = screen.getByText('Machine Learning').closest('.constellation-node');
    fireEvent.click(mlNode);

    // Verify detail panel opens
    await waitFor(() => {
      expect(screen.getByText('AI and neural networks')).toBeInTheDocument();
    });

    // Click outside on body
    fireEvent.mouseDown(document.body);

    // Verify detail panel closes
    await waitFor(() => {
      expect(screen.queryByText('AI and neural networks')).not.toBeInTheDocument();
    });
  });
});
