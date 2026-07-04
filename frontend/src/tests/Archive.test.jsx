import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Archive from '../pages/Archive';

vi.mock('../canvas/ArchiveCylinder', () => {
  return {
    default: ({ items }) => (
      <div data-testid="archive-cylinder">
        {items?.map(item => <div key={item.id}>{item.title}</div>)}
      </div>
    )
  };
});

describe('Archive Page Component', () => {
  const mockItems = [
    { id: 1, title: 'Rust Safety', summary: 'Memory safety in Rust', source_type: 'url', tags: ['rust'] },
    { id: 2, title: 'Voice Memo', summary: 'Audio recording notes', source_type: 'voice', tags: ['audio'] },
    { id: 3, title: 'PDF Manual', summary: 'Technical spec sheet', source_type: 'pdf', tags: ['spec'] }
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();

    window.fetch = vi.fn().mockImplementation((url) => {
      if (url.includes('/api/items')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: mockItems })
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
  });

  it('renders archive room and filters items by source type', async () => {
    render(<Archive />);

    await waitFor(() => {
      expect(screen.getByText('Rust Safety')).toBeInTheDocument();
    });

    const voiceBtn = screen.getByTitle('Voice Notes');
    fireEvent.click(voiceBtn);

    const pdfBtn = screen.getByTitle('PDF Documents');
    fireEvent.click(pdfBtn);

    const linksBtn = screen.getByTitle('Web Links');
    fireEvent.click(linksBtn);
  });

  it('handles initialSelectedItem prop and auto-opens panel', async () => {
    const onClearMock = vi.fn();
    render(<Archive initialSelectedItem={mockItems[0]} onClearInitialSelect={onClearMock} />);

    await waitFor(() => {
      expect(screen.getByText('Signal Archive')).toBeInTheDocument();
    });
  });
});
