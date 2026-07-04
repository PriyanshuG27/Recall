import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import TransmissionCard from '../components/TransmissionCard';

describe('TransmissionCard Component', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(performance, 'now').mockImplementation(() => Date.now());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  const mockCard = {
    id: 1,
    question: 'What is the capital of France?',
    answer: 'Paris',
    source_type: 'text'
  };

  it('returns null if card is falsy', () => {
    const { container } = render(<TransmissionCard card={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders front face with question and reveal button by default', () => {
    const handleReveal = vi.fn();
    render(
      <TransmissionCard
        card={mockCard}
        cardNumber={1}
        totalCards={10}
        revealed={false}
        onReveal={handleReveal}
      />
    );

    expect(screen.getByText('What is the capital of France?')).toBeInTheDocument();
    expect(screen.getAllByText('TRANSMISSION 01 / 10').length).toBeGreaterThan(0);
    
    const revealBtn = screen.getByRole('button', { name: /Reveal/i });
    fireEvent.click(revealBtn);
    expect(handleReveal).toHaveBeenCalledTimes(1);
  });

  it('renders back face with answer and rating buttons when revealed is true', () => {
    const handleRate = vi.fn();
    render(
      <TransmissionCard
        card={mockCard}
        cardNumber={1}
        totalCards={10}
        revealed={true}
        onRate={handleRate}
      />
    );

    act(() => {
      vi.advanceTimersByTime(200);
    });

    expect(screen.getByText('Paris')).toBeInTheDocument();

    const rateBtn = screen.getByRole('button', { name: /1 LOCKED IN/i });
    fireEvent.click(rateBtn);
    expect(handleRate).toHaveBeenCalledWith(1);
  });

  it('renders formatted answer with options and explanation', () => {
    const quizCard = {
      id: 2,
      front: 'Which language is used for web styling?',
      options: ['HTML', 'CSS', 'JS'],
      correct_index: 1,
      explanation: 'CSS stands for Cascading Style Sheets'
    };

    render(
      <TransmissionCard
        card={quizCard}
        cardNumber={2}
        totalCards={5}
        revealed={true}
        onRate={vi.fn()}
      />
    );

    act(() => {
      vi.advanceTimersByTime(200);
    });

    expect(screen.getAllByText(/CSS/)[0]).toBeInTheDocument();
    expect(screen.getByText(/Cascading Style Sheets/)).toBeInTheDocument();
  });
});
