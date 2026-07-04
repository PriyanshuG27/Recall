import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import NodePanel from '../components/NodePanel';

const mockNode = {
  id: 123,
  title: 'Understanding Spaced Repetition',
  source_type: 'url',
  summary: 'A detailed article explaining the neuroscience of spaced repetition and the SM-2 algorithm.',
  source_url: 'https://supermemo.com/english/ol/sm2.htm',
  tags: ['learning', 'memory', 'productivity'],
  created_at: '2026-06-25T14:30:00Z',
  bookmarked: false,
  quiz: {
    id: 10,
    question: 'What does the SM-2 algorithm schedule?',
    options: [
      'Task lists',
      'Spaced repetition reviews',
      'Database backups',
      'API rate limits'
    ],
    correct_index: 1,
    explanation: 'SM-2 computes intervals for spaced repetition learning review cards.'
  }
};

describe('NodePanel Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url) => {
      if (url.includes('/quiz/answer')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ correct: true }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) });
    }));
  });

  it('renders nothing when node is null', () => {
    const { container } = render(<NodePanel node={null} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders mock node data and matches snapshot', () => {
    render(<NodePanel node={mockNode} onClose={vi.fn()} />);
    
    // Expect panel structure
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Understanding Spaced Repetition')).toBeInTheDocument();
    
    // Summary
    expect(screen.getByText(/A detailed article explaining the neuroscience/i)).toBeInTheDocument();
    
    // Source URL link
    const sourceLink = screen.getByRole('link', { name: /View Source/i });
    expect(sourceLink).toBeInTheDocument();
    expect(sourceLink).toHaveAttribute('href', 'https://supermemo.com/english/ol/sm2.htm');
    
    // Tags
    expect(screen.getByText(/#learning/i)).toBeInTheDocument();
    expect(screen.getByText(/#memory/i)).toBeInTheDocument();
    
    // Quick-action buttons (new QuickAction bar with title attributes)
    expect(screen.getByTitle('Quiz')).toBeInTheDocument();
    expect(screen.getByTitle('Remind')).toBeInTheDocument();
  });

  it('triggers onClose when close button is clicked', () => {
    const onCloseMock = vi.fn();
    render(<NodePanel node={mockNode} onClose={onCloseMock} />);
    
    const closeBtn = screen.getByRole('button', { name: /Close panel/i });
    fireEvent.click(closeBtn);
    expect(onCloseMock).toHaveBeenCalled();
  });

  it('triggers onClose when Escape key is pressed', () => {
    const onCloseMock = vi.fn();
    render(<NodePanel node={mockNode} onClose={onCloseMock} />);
    
    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });
    expect(onCloseMock).toHaveBeenCalled();
  });

  it('toggles the reminder input form and submits a new reminder', async () => {
    render(<NodePanel node={mockNode} onClose={vi.fn()} />);
    // Open reminder form via the QuickAction "Remind" button
    const reminderBtn = screen.getByTitle('Remind');
    fireEvent.click(reminderBtn);
    
    expect(screen.getByText('Message')).toBeInTheDocument();
    expect(screen.getByText('Remind At')).toBeInTheDocument();
    
    // Form elements
    const messageInput = screen.getByDisplayValue('Review: Understanding Spaced Repetition');
    const timeInput = screen.getByLabelText(/Remind At/i);
    
    fireEvent.change(messageInput, { target: { value: 'Review spaced repetition article' } });
    fireEvent.change(timeInput, { target: { value: '2026-06-30T10:00' } });
    
    const saveBtn = screen.getByRole('button', { name: /Confirm Reminder/i });
    fireEvent.click(saveBtn);
    
    expect(fetch).toHaveBeenCalledWith('/api/reminders', expect.objectContaining({
      method: 'POST'
    }));
  });

  it('opens and answers quiz correctly', async () => {
    render(<NodePanel node={mockNode} onClose={vi.fn()} />);
    
    const openQuizBtn = screen.getByTitle('Quiz');
    fireEvent.click(openQuizBtn);
    
    expect(screen.getByText('What does the SM-2 algorithm schedule?')).toBeInTheDocument();
    
    // Find correct option and click it
    const correctBtn = screen.getByRole('button', { name: 'Spaced repetition reviews' });
    fireEvent.click(correctBtn);
    
    expect(screen.getByText('Correct')).toBeInTheDocument();
    expect(screen.getByText('SM-2 computes intervals for spaced repetition learning review cards.')).toBeInTheDocument();
  });

  it('handles copy summary action', async () => {
    const writeTextMock = vi.fn().mockResolvedValue();
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(<NodePanel node={mockNode} onClose={vi.fn()} />);

    const copyBtn = screen.getByTitle(/Copy/i);
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledWith(mockNode.summary);
  });

  it('handles delete signal with confirmation', async () => {
    const onCloseMock = vi.fn();
    render(<NodePanel node={mockNode} onClose={onCloseMock} />);

    const deleteBtn = screen.getByTitle(/Delete/i);
    fireEvent.click(deleteBtn);

    // Confirmation dialog should be open
    const confirmDeleteBtn = screen.getByRole('button', { name: /Yes, Delete/i });
    fireEvent.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/items/123', expect.objectContaining({ method: 'DELETE' }));
      expect(onCloseMock).toHaveBeenCalled();
    });
  });
});
