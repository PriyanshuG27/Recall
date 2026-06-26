import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
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
    vi.clearAllMocks();
  });

  it('renders nothing when node is null', () => {
    const { container } = render(<NodePanel node={null} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders mock node data and matches snapshot', () => {
    const { container } = render(<NodePanel node={mockNode} onClose={vi.fn()} />);
    
    // Expect panel structure
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Understanding Spaced Repetition')).toBeInTheDocument();
    
    // Summary
    expect(screen.getByText(/A detailed article explaining the neuroscience/i)).toBeInTheDocument();
    
    // Source Link badge
    expect(screen.getAllByTestId('icon-Link')[0]).toBeInTheDocument();
    
    // Source URL
    const sourceLink = screen.getByRole('link', { name: /View Source/i });
    expect(sourceLink).toBeInTheDocument();
    expect(sourceLink).toHaveAttribute('href', 'https://supermemo.com/english/ol/sm2.htm');
    
    // Tags
    expect(screen.getByText('#learning')).toBeInTheDocument();
    expect(screen.getByText('#memory')).toBeInTheDocument();
    expect(screen.getByText('#productivity')).toBeInTheDocument();
    
    // Buttons
    expect(screen.getByRole('button', { name: /Open Quiz/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Set Reminder/i })).toBeInTheDocument();
    
    expect(container).toMatchSnapshot();
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
    
    // Open reminder form
    const reminderBtn = screen.getByRole('button', { name: /Set Reminder/i });
    fireEvent.click(reminderBtn);
    
    expect(screen.getByText('Message')).toBeInTheDocument();
    expect(screen.getByText('Remind At')).toBeInTheDocument();
    
    // Form elements
    const messageInput = screen.getByDisplayValue('Review: Understanding Spaced Repetition');
    const timeInput = screen.getByLabelText(/Remind At/i);
    
    fireEvent.change(messageInput, { target: { value: 'Review spaced repetition article' } });
    fireEvent.change(timeInput, { target: { value: '2026-06-30T10:00' } });
    
    // Mock response
    window.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'success' })
    });
    
    const saveBtn = screen.getByRole('button', { name: /Save Reminder/i });
    fireEvent.click(saveBtn);
    
    // Expect fetch to be called
    expect(window.fetch).toHaveBeenCalledWith('/api/reminders', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        item_id: 123,
        message: 'Review spaced repetition article',
        remind_at: new Date('2026-06-30T10:00').toISOString()
      })
    }));
  });

  it('opens and interacts with the quiz', () => {
    render(<NodePanel node={mockNode} onClose={vi.fn()} />);
    
    const openQuizBtn = screen.getByRole('button', { name: /Open Quiz/i });
    fireEvent.click(openQuizBtn);
    
    expect(screen.getByText('What does the SM-2 algorithm schedule?')).toBeInTheDocument();
    
    // Find correct and incorrect options
    const correctBtn = screen.getByRole('button', { name: 'Spaced repetition reviews' });
    
    fireEvent.click(correctBtn);
    expect(screen.getByText('Correct!')).toBeInTheDocument();
    expect(screen.getByText('SM-2 computes intervals for spaced repetition learning review cards.')).toBeInTheDocument();
  });
});
