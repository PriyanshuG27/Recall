import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Map from '../pages/Map';

// Mock MapCanvas to avoid canvas rendering and D3 physics timer loops
vi.mock('../canvas/MapCanvas', () => {
  return {
    default: ({ onNodeClick }) => (
      <div data-testid="mock-map-canvas">
        <button onClick={() => onNodeClick?.({ id: 10, title: 'Map Signal', source_type: 'url' })}>Click Item Node</button>
        <button onClick={() => onNodeClick?.({ id: 'hub-javascript', title: 'javascript', type: 'hub', memberCount: 2, icon: '⚡' })}>Click Hub Node</button>
      </div>
    )
  };
});

describe('Map Page Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url) => {
      if (url.includes('/api/user/profile')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ pulse_score: 88 }) });
      }
      if (url.includes('/api/candidates/active')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ id: 1, title: 'Candidate 1' }]) });
      }
      if (url.includes('/api/tags/portraits')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ javascript: { icon: '⚡' } }) });
      }
      if (url.includes('/api/items')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([
            { id: 10, title: 'Map Signal', summary: 'This is on map', source_type: 'url', tags: ['javascript', 'web'] },
            { id: 11, title: 'Voice Signal', summary: 'Audio record', source_type: 'voice', tags: ['javascript'] }
          ])
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }));
  });

  it('renders Knowledge Constellation and handles source filter chip clicks', async () => {
    render(<Map />);

    await waitFor(() => {
      expect(screen.getByText('Knowledge Constellation')).toBeInTheDocument();
    });

    const linksFilter = screen.queryByRole('button', { name: /LINKS|URL/i });
    if (linksFilter) {
      fireEvent.click(linksFilter);
    }
  });

  it('handles item node click and opens node panel', async () => {
    render(<Map />);

    await waitFor(() => {
      expect(screen.getByText('Knowledge Constellation')).toBeInTheDocument();
    });

    const clickItemBtn = screen.getByText('Click Item Node');
    fireEvent.click(clickItemBtn);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  it('handles hub node click and opens Hub Panel', async () => {
    render(<Map />);

    await waitFor(() => {
      expect(screen.getByText('Knowledge Constellation')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText(/2 Signals Catalogued/i)).toBeInTheDocument();
    });

    const clickHubBtn = screen.getByText('Click Hub Node');
    fireEvent.click(clickHubBtn);

    await waitFor(() => {
      expect(screen.getByText('Knowledge Cluster')).toBeInTheDocument();
    });

    const closeHubBtn = screen.getByRole('button', { name: '×' });
    fireEvent.click(closeHubBtn);
  });
});
