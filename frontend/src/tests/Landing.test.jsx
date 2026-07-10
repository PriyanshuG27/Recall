import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Landing from '../pages/Landing';

// Mock Lenis scroll library to prevent JSDOM errors
vi.mock('lenis', () => {
  class MockLenis {
    raf() {}
    destroy() {}
  }
  return {
    default: MockLenis,
  };
});

describe('Landing Page Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders landing sections correctly', () => {
    render(<Landing />);

    // Header logo
    expect(screen.getByText('Atrium', { selector: '.lp-logo' })).toBeInTheDocument();
    
    // Beta Badge
    expect(screen.getByText(/Now in private beta/i)).toBeInTheDocument();

    // Stats Section
    expect(screen.getByText('signals saved')).toBeInTheDocument();
    expect(screen.getByText('to process any file')).toBeInTheDocument();
    expect(screen.getByText('encrypted at rest')).toBeInTheDocument();

    // Bento Card Headers
    expect(screen.getByText('Zero friction capture')).toBeInTheDocument();
    expect(screen.getByText('Private by design')).toBeInTheDocument();
    expect(screen.getByText('Export anytime')).toBeInTheDocument();
    expect(screen.getByText('Voice → knowledge')).toBeInTheDocument();
    expect(screen.getByText('Ask your archive')).toBeInTheDocument();
  });

  it('interacts with the Security Showcase tabs correctly', async () => {
    render(<Landing />);

    // Verify initial tab (Zero-Trust Storage)
    expect(screen.getByRole('heading', { name: 'Zero-Trust Storage' })).toBeInTheDocument();
    expect(screen.getByText(/All ingested user texts and external tokens are encrypted at rest/i)).toBeInTheDocument();
    expect(screen.getByText(/# Client-side encryption key is separate/i)).toBeInTheDocument();

    // Click PII & Secret Scrubbing tab
    const piiTab = screen.getByRole('button', { name: /PII & Secret Scrubbing/i });
    fireEvent.click(piiTab);

    // Verify tab transition to PII
    expect(screen.getByRole('heading', { name: 'PII & Secret Scrubbing' })).toBeInTheDocument();
    expect(screen.getByText(/System logs, error streams, and telemetry traces are automatically sanitized/i)).toBeInTheDocument();
    expect(screen.getByText(/# Log stream processor matches patterns/i)).toBeInTheDocument();

    // Click SSRF & DNS-Pinning tab
    const ssrfTab = screen.getByRole('button', { name: /SSRF & DNS-Pinning/i });
    fireEvent.click(ssrfTab);

    // Verify tab transition to SSRF
    expect(screen.getByRole('heading', { name: 'SSRF & DNS-Pinning' })).toBeInTheDocument();
    expect(screen.getByText(/Web scraping links is a major SSRF risk/i)).toBeInTheDocument();
    expect(screen.getByText(/# Block private ranges/i)).toBeInTheDocument();
  });

  it('animates the lock bento card private graphic on click', () => {
    render(<Landing />);

    // Find secure system indicator
    const secureText = screen.getByText('System Secure');
    expect(secureText).toBeInTheDocument();
    
    const lockDiv = screen.getByText('🔒');
    expect(lockDiv).toBeInTheDocument();

    // Click to decrypt
    fireEvent.click(lockDiv);

    // Verify indicator updates
    expect(screen.getByText('🔓')).toBeInTheDocument();
    expect(screen.getByText('Decrypting...')).toBeInTheDocument();
  });

  it('runs the backup progress simulation on click', async () => {
    render(<Landing />);

    // Click triggers simulation
    const exportBtn = screen.getByText(/⚡ Click to backup archive/i);
    expect(exportBtn).toBeInTheDocument();

    fireEvent.click(exportBtn);

    // Verify loader terminal text
    expect(screen.getByText('$ atrium --export-zip')).toBeInTheDocument();
  });

  it('cycles questions on the Ask Bento card graphic click', () => {
    render(<Landing />);

    const askCard = screen.getByText('what did I save about sleep?');
    expect(askCard).toBeInTheDocument();

    // Click ask card triggers transition/cycle
    fireEvent.click(askCard);

    // Verify it changed to typing state or next query
    expect(screen.getByText('[Cycle]')).toBeInTheDocument();
  });

  it('triggers router transition on Sign In or Enter Atrium click', () => {
    const pushStateSpy = vi.spyOn(window.history, 'pushState');
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    render(<Landing />);

    // Click "Sign in" in the nav bar
    const signInBtn = screen.getAllByRole('button', { name: /Sign in/i })[0];
    fireEvent.click(signInBtn);

    expect(pushStateSpy).toHaveBeenCalledWith({}, '', '/login');
    expect(dispatchSpy).toHaveBeenCalledWith(expect.any(PopStateEvent));
  });
});
