import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ChatDrawer from '../components/ChatDrawer';

describe('ChatDrawer RAG Assistant', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Liquid Orb when closed', () => {
    const mockOnClose = vi.fn();
    render(<ChatDrawer isOpen={false} onClose={mockOnClose} />);

    // Check that the floating assistant label is visible
    expect(screen.getByText('ASSISTANT')).toBeInTheDocument();

    // Click on the orb and verify that onClose callback (toggle) is triggered
    const orbWrapper = screen.getByText('ASSISTANT').parentElement;
    fireEvent.click(orbWrapper);
    expect(mockOnClose).toHaveBeenCalledTimes(1);
  });

  it('renders empty standby state when open with no history', () => {
    render(<ChatDrawer isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByText('ASSISTANT: ACTIVE')).toBeInTheDocument();
    expect(screen.getByText(/> INITIALIZING COGNITIVE CORE\.\.\./i)).toBeInTheDocument();
  });

  it('submits a query and renders response with interactive citations and sources list', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: 'Based on your notes, Stoicism leads to eudaimonia [1].',
        sources: [
          {
            id: 101,
            title: 'Stoicism Introduction',
            summary: 'Stoicism teaches that eudaimonia is found in acceptance.',
            tags: ['philosophy', 'stoic']
          }
        ]
      })
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<ChatDrawer isOpen={true} onClose={vi.fn()} />);

    // Type query
    const input = screen.getByPlaceholderText('Ask anything...');
    fireEvent.change(input, { target: { value: 'what is stoicism?' } });

    // Submit form
    const sendBtn = screen.getByText('[ SEND ]');
    fireEvent.click(sendBtn);

    // Verify user message displays
    expect(screen.getByText('what is stoicism?')).toBeInTheDocument();

    // Wait for AI response to load
    await waitFor(() => {
      expect(screen.getByText(/Based on your notes, Stoicism leads to eudaimonia/)).toBeInTheDocument();
    });

    // Check that citation badge [1] exists
    const citation = screen.getByRole('button', { name: '[1]' });
    expect(citation).toBeInTheDocument();

    // Check that retrieved sources section is rendered
    expect(screen.getByText('// RETRIEVED SOURCES')).toBeInTheDocument();
    expect(screen.getByText('Stoicism Introduction')).toBeInTheDocument();
    expect(screen.getByText('Stoicism teaches that eudaimonia is found in acceptance.')).toBeInTheDocument();
    expect(screen.getByText('#philosophy')).toBeInTheDocument();
  });

  it('highlights the source card when citation badge is clicked', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: 'Here is the details [1].',
        sources: [
          {
            id: 102,
            title: 'RAG Optimization Guide',
            summary: 'RAG works best with proper chunk sizes.',
            tags: ['rag']
          }
        ]
      })
    });
    vi.stubGlobal('fetch', mockFetch);

    // Mock scrollIntoView
    window.HTMLElement.prototype.scrollIntoView = vi.fn();

    render(<ChatDrawer isOpen={true} onClose={vi.fn()} />);

    const input = screen.getByPlaceholderText('Ask anything...');
    fireEvent.change(input, { target: { value: 'optimizing rag' } });
    fireEvent.click(screen.getByText('[ SEND ]'));

    await waitFor(() => {
      expect(screen.getByText('RAG Optimization Guide')).toBeInTheDocument();
    });

    // Click citation badge
    const citation = screen.getByRole('button', { name: '[1]' });
    fireEvent.click(citation);

    // Check that source card wrapper contains high-contrast highlighted border class
    const sourceCard = screen.getByText('RAG Optimization Guide').closest('.assistant-source-card');
    expect(sourceCard).toHaveClass('highlighted');
  });

  it('renders dynamic node count in boot log when totalSaves prop is passed', () => {
    render(<ChatDrawer isOpen={true} onClose={vi.fn()} totalSaves={72} />);
    expect(screen.getByText(/> KNOWLEDGE CACHE: 72 NODES INDEXED/i)).toBeInTheDocument();
  });

  it('triggers onOpen when LiquidOrb is clicked while closed', () => {
    const mockOnOpen = vi.fn();
    render(<ChatDrawer isOpen={false} onOpen={mockOnOpen} onClose={vi.fn()} />);
    
    const orbWrapper = screen.getByText('ASSISTANT').parentElement;
    fireEvent.click(orbWrapper);
    expect(mockOnOpen).toHaveBeenCalledTimes(1);
  });

  it('renders clickable link class and arrow when source has source_url', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: 'Reference [1].',
        sources: [
          {
            id: 103,
            title: 'Recall Github Repository',
            summary: 'Github repo holding the code.',
            source_url: 'https://github.com/PriyanshuG27/Recall',
            tags: ['git']
          }
        ]
      })
    });
    vi.stubGlobal('fetch', mockFetch);
    vi.spyOn(window, 'open').mockImplementation(() => {});

    render(<ChatDrawer isOpen={true} onClose={vi.fn()} />);
    const input = screen.getByPlaceholderText('Ask anything...');
    fireEvent.change(input, { target: { value: 'github url' } });
    fireEvent.click(screen.getByText('[ SEND ]'));

    await waitFor(() => {
      expect(screen.getByText('Recall Github Repository')).toBeInTheDocument();
    });

    // Check that title has clickable link class and external arrow
    const titleEl = screen.getByText(/Recall Github Repository/);
    expect(titleEl).toHaveClass('clickable-link');
    expect(screen.getByText('↗')).toBeInTheDocument();

    // Click the title and verify window.open is called
    fireEvent.click(titleEl);
    expect(window.open).toHaveBeenCalledWith('https://github.com/PriyanshuG27/Recall', '_blank');
  });

  it('triggers onItemSelect when a source card is clicked', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: 'Here is the details [1].',
        sources: [
          {
            id: 104,
            title: 'Card Click Guide',
            summary: 'Clicking cards triggers item selection.',
            tags: ['interactive']
          }
        ]
      })
    });
    vi.stubGlobal('fetch', mockFetch);
    window.HTMLElement.prototype.scrollIntoView = vi.fn();

    const mockOnItemSelect = vi.fn();
    render(<ChatDrawer isOpen={true} onClose={vi.fn()} onItemSelect={mockOnItemSelect} />);

    const input = screen.getByPlaceholderText('Ask anything...');
    fireEvent.change(input, { target: { value: 'click guide' } });
    fireEvent.click(screen.getByText('[ SEND ]'));

    await waitFor(() => {
      expect(screen.getByText('Card Click Guide')).toBeInTheDocument();
    });

    const sourceCard = screen.getByText('Card Click Guide').closest('.assistant-source-card');
    fireEvent.click(sourceCard);

    expect(mockOnItemSelect).toHaveBeenCalledTimes(1);
    expect(mockOnItemSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 104, title: 'Card Click Guide' }));
  });
});
