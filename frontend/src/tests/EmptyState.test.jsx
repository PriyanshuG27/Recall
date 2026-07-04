import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import EmptyState from '../components/EmptyState';

describe('EmptyState Component', () => {
  beforeEach(() => {
    import.meta.env.VITE_BOT_USERNAME = 'TestRecallBot';
  });

  it('renders graph empty state with pulsing node, text, and bot URL', () => {
    render(<EmptyState variant="graph" />);

    expect(screen.getByTestId('empty-state-graph')).toBeInTheDocument();
    expect(screen.getByText('Your constellation is empty')).toBeInTheDocument();
    expect(
      screen.getByText(/Forward any link, voice note, or PDF to your Telegram bot/i)
    ).toBeInTheDocument();

    const linkButton = screen.getByRole('link', { name: /Open Telegram Bot/i });
    expect(linkButton).toBeInTheDocument();
    expect(linkButton).toHaveAttribute('href', 'https://t.me/TestRecallBot');
  });

  it('uses default fallback bot username when env variable is empty', () => {
    import.meta.env.VITE_BOT_USERNAME = '';
    render(<EmptyState variant="graph" />);

    const linkButton = screen.getByRole('link', { name: /Open Telegram Bot/i });
    expect(linkButton).toHaveAttribute('href', 'https://t.me/RecallTestEnvBot');
  });

  it('renders feed empty state with magnifying glass and text', () => {
    render(<EmptyState variant="feed" />);

    expect(screen.getByTestId('empty-state-feed')).toBeInTheDocument();
    expect(screen.getByText('Nothing found')).toBeInTheDocument();
  });

  it('renders search empty state with query injected in text', () => {
    render(<EmptyState variant="search" query="quantum computing" />);

    expect(screen.getByTestId('empty-state-search')).toBeInTheDocument();
    expect(screen.getByText("No results for 'quantum computing'")).toBeInTheDocument();
  });

  it('returns null for unknown variant', () => {
    const { container } = render(<EmptyState variant="unknown" />);
    expect(container.firstChild).toBeNull();
  });
});
