import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import SearchOverlay from '../components/SearchOverlay';

const addToastMock = vi.fn();

vi.mock('../components/Toast', () => ({
  useToast: () => ({
    addToast: addToastMock,
  })
}));

describe('SearchOverlay Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url, opts) => {
      if (url.includes('/api/tags')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ tag: 'tag1', count: 3 }, { tag: 'tag2', count: 1 }]) });
      }
      if (url.includes('/api/search')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([
            { id: 1, title: 'Rust Safety', summary: 'Safe memory management', source_type: 'url', tags: ['rust'] },
            { id: 2, title: 'Audio Clip', summary: 'Voice record', source_type: 'voice', tags: ['audio'] }
          ])
        });
      }
      if (url.includes('/api/extension/save')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 100, title: 'New Note' }) });
      }
      return Promise.resolve({ ok: true });
    }));
  });

  it('renders correctly and searches for items', async () => {
    render(<SearchOverlay onClose={vi.fn()} onItemSelect={vi.fn()} />);

    const searchInput = screen.getByPlaceholderText(/Search signals or type/i);
    fireEvent.change(searchInput, { target: { value: 'Rust' } });

    // Wait for the fuzzy search results to load
    await waitFor(() => {
      expect(screen.getByText('Rust')).toBeInTheDocument();
    });
  });

  it('handles source filter clicking and item selection', async () => {
    const onItemSelectMock = vi.fn();
    const onCloseMock = vi.fn();

    render(<SearchOverlay onClose={onCloseMock} onItemSelect={onItemSelectMock} />);

    const searchInput = screen.getByPlaceholderText(/Search signals or type/i);
    fireEvent.change(searchInput, { target: { value: 'Rust' } });

    await waitFor(() => {
      expect(screen.getByText('Rust')).toBeInTheDocument();
    });

    // Click VOICE filter button
    const voiceFilterBtns = screen.getAllByRole('button', { name: /VOICE/i });
    fireEvent.click(voiceFilterBtns[0]);

    // Item selection
    const voiceCard = screen.getByText(/Audio Clip/i);
    fireEvent.click(voiceCard);

    expect(onItemSelectMock).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }));
    expect(onCloseMock).toHaveBeenCalled();
  });

  it('navigates search results with keyboard ArrowDown, ArrowUp and Enter', async () => {
    const onItemSelectMock = vi.fn();
    render(<SearchOverlay onClose={vi.fn()} onItemSelect={onItemSelectMock} />);

    const searchInput = screen.getByPlaceholderText(/Search signals or type/i);
    fireEvent.change(searchInput, { target: { value: 'Rust' } });

    await waitFor(() => {
      expect(screen.getByText('Rust')).toBeInTheDocument();
    });

    // Press ArrowDown then Enter
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    fireEvent.keyDown(window, { key: 'Enter' });

    expect(onItemSelectMock).toHaveBeenCalled();
  });

  it('handles Command Mode actions and execution', async () => {
    const onCloseMock = vi.fn();
    render(<SearchOverlay onClose={onCloseMock} onItemSelect={vi.fn()} />);

    const searchInput = screen.getByPlaceholderText(/Search signals or type/i);
    fireEvent.change(searchInput, { target: { value: '/' } });

    expect(screen.getByText(/Start Review Drill/i)).toBeInTheDocument();
    expect(screen.getByText(/Export Signals Backup/i)).toBeInTheDocument();

    // Select action via Enter
    fireEvent.keyDown(window, { key: 'Enter' });
  });

  it('opens and submits Create Note form inside command overlay', async () => {
    render(<SearchOverlay onClose={vi.fn()} onItemSelect={vi.fn()} />);

    // Click "Add a note" quick action button in empty state
    const addNoteBtn = screen.getByRole('button', { name: /Add a note/i });
    fireEvent.click(addNoteBtn);

    // Should switch to create-note view
    const titleInput = screen.getByPlaceholderText(/Note Title/i);
    const contentTextarea = screen.getByPlaceholderText(/Type your note content/i);

    fireEvent.change(titleInput, { target: { value: 'My Test Note' } });
    fireEvent.change(contentTextarea, { target: { value: 'Some note details here...' } });

    const submitBtn = screen.getByRole('button', { name: /SAVE NOTE/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/extension/save', expect.anything());
    });
  });

  it('handles recent search queries clicking and clearing', async () => {
    localStorage.setItem('recall-recent-searches', JSON.stringify(['previous query']));

    render(<SearchOverlay onClose={vi.fn()} onItemSelect={vi.fn()} />);

    expect(screen.getByText('previous query')).toBeInTheDocument();

    // Clear all recent searches
    const clearAllBtn = screen.getByRole('button', { name: /Clear All/i });
    fireEvent.click(clearAllBtn);
    expect(localStorage.getItem('recall-recent-searches')).toBe(null);
  });
});
