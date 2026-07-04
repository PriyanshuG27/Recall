import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import PWAInstallBanner from '../components/PWAInstallBanner';

describe('PWAInstallBanner Component', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('renders nothing by default when beforeinstallprompt is not fired', () => {
    const { container } = render(<PWAInstallBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('shows banner when beforeinstallprompt event is dispatched and installs app', async () => {
    render(<PWAInstallBanner />);

    const mockPromptEvent = new Event('beforeinstallprompt');
    mockPromptEvent.prompt = vi.fn();
    mockPromptEvent.userChoice = Promise.resolve({ outcome: 'accepted' });

    act(() => {
      window.dispatchEvent(mockPromptEvent);
    });

    expect(screen.getByText('Install Recall')).toBeInTheDocument();

    const installBtn = screen.getByRole('button', { name: 'Install' });
    await act(async () => {
      fireEvent.click(installBtn);
    });

    expect(mockPromptEvent.prompt).toHaveBeenCalled();
  });

  it('dismisses banner on close button click and sets sessionStorage', () => {
    render(<PWAInstallBanner />);

    const mockPromptEvent = new Event('beforeinstallprompt');
    mockPromptEvent.prompt = vi.fn();
    mockPromptEvent.userChoice = Promise.resolve({ outcome: 'dismissed' });

    act(() => {
      window.dispatchEvent(mockPromptEvent);
    });

    const closeBtn = screen.getByRole('button', { name: 'Close' });
    fireEvent.click(closeBtn);

    expect(sessionStorage.getItem('recall_pwa_banner_dismissed')).toBe('true');
    expect(screen.queryByText('Install Recall')).not.toBeInTheDocument();
  });
});
