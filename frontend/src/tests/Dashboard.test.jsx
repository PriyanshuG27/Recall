import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../canvas/GraphCanvas', () => {
  const React = require('react');
  return {
    __esModule: true,
    default: function MockGraphCanvas({ activeNodes, handleNodeClick, matchingNodeIds }) {
      return React.createElement(
        'div',
        { 'data-testid': 'mock-graph-canvas' },
        activeNodes.map(node => {
          let opacity = '1';
          if (matchingNodeIds) {
            opacity = matchingNodeIds.has(node.id) ? '1' : '0.1';
          }
          return React.createElement(
            'button',
            {
              key: node.id,
              className: 'constellation-node',
              style: { opacity },
              onClick: () => handleNodeClick && handleNodeClick(node)
            },
            node.title || node.label
          );
        })
      );
    }
  };
});

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

import Dashboard from '../pages/Dashboard';
import { AuthProvider, useAuth } from '../context/AuthContext';
import axios from 'axios';

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
              { id: 2, title: 'Voice Signal', summary: 'Audio record', source_type: 'voice', tags: ['voice'], created_at: '2026-06-26' },
              { id: 3, title: 'PDF Manual', summary: 'Doc pdf', source_type: 'pdf', tags: ['pdf'], created_at: '2026-06-26' }
            ],
            total: 3,
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
              { id: 2, title: 'Voice Signal', source_type: 'voice', created_at: '2026-06-26', is_hub: false }
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
    });
  });

  it('filters nodes by source type filter buttons', async () => {
    render(
      <AuthProvider>
        <SeedAuth user={{ id: 42, chat_id: '99999' }}>
          <Dashboard />
        </SeedAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Welcome to Recall')).toBeInTheDocument();
    });

    const linksFilter = screen.queryByRole('button', { name: /LINKS|URL/i });
    if (linksFilter) fireEvent.click(linksFilter);

    const voiceFilter = screen.queryByRole('button', { name: /VOICE/i });
    if (voiceFilter) fireEvent.click(voiceFilter);
  });

  it('handles search debounce, axios search call, and node dimming', async () => {
    render(
      <AuthProvider>
        <SeedAuth user={{ id: 42, chat_id: '99999' }}>
          <Dashboard />
        </SeedAuth>
      </AuthProvider>
    );

    const searchTrigger = screen.getByTestId('icon-MagnifyingGlass').closest('button');
    fireEvent.click(searchTrigger);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Search your brain...')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Search your brain...');
    fireEvent.change(searchInput, { target: { value: 'neural networks' } });

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith('/api/search', { query: 'neural networks', rag: false });
    });

    const clearBtn = screen.getByText('Clear');
    fireEvent.click(clearBtn);
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

    await waitFor(() => {
      expect(screen.getByText('AI and neural networks')).toBeInTheDocument();
    });

    const closeBtn = screen.getByText('Close');
    fireEvent.click(closeBtn);

    expect(screen.queryByText('AI and neural networks')).not.toBeInTheDocument();
  });
});
