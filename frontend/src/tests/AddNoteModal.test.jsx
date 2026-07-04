import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AddNoteModal from '../components/AddNoteModal';

// Mock useToast hook
vi.mock('../components/Toast', () => ({
  useToast: () => ({
    addToast: vi.fn(),
  })
}));

describe('AddNoteModal Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(['tag1', 'tag2'])
      })
    ));
  });

  it('renders modal correctly with empty fields', async () => {
    render(<AddNoteModal onClose={vi.fn()} onSuccess={vi.fn()} />);

    expect(screen.getByPlaceholderText(/Signal Title/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Type or paste your note details/i)).toBeInTheDocument();
  });

  it('handles user typing and saves new note successfully', async () => {
    const handleSuccess = vi.fn();
    const handleClose = vi.fn();

    const mockSavedItem = { id: 123, title: 'New note title', raw_text: 'Body of the note' };

    // Mock fetch specifically for the post request
    vi.stubGlobal('fetch', vi.fn()
      .mockImplementationOnce(() => Promise.resolve({ ok: true, json: () => Promise.resolve([]) })) // /api/tags
      .mockImplementationOnce(() => Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve(mockSavedItem) })) // /api/items
    );

    render(<AddNoteModal onClose={handleClose} onSuccess={handleSuccess} />);

    // Type Title
    fireEvent.change(screen.getByPlaceholderText(/Signal Title/i), {
      target: { value: 'New note title' }
    });

    // Type Body
    fireEvent.change(screen.getByPlaceholderText(/Type or paste your note details/i), {
      target: { value: 'Body of the note' }
    });

    // Type tags and hit Enter
    const tagInput = screen.getByPlaceholderText(/Type tag and press Enter/i);
    fireEvent.change(tagInput, { target: { value: 'cool' } });
    fireEvent.keyDown(tagInput, { key: 'Enter', code: 'Enter' });

    // Submit form
    fireEvent.click(screen.getByRole('button', { name: /ADD SIGNAL/i }));

    await waitFor(() => {
      expect(handleSuccess).toHaveBeenCalledWith(mockSavedItem);
      expect(handleClose).toHaveBeenCalled();
    });
  });

  it('triggers onClose when Escape key is pressed', () => {
    const handleClose = vi.fn();
    render(<AddNoteModal onClose={handleClose} onSuccess={vi.fn()} />);

    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });
    expect(handleClose).toHaveBeenCalled();
  });
});
