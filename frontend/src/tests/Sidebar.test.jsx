import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import Sidebar from '../components/Sidebar';

// Mock useAuth hook
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { username: 'observer' },
    logout: vi.fn(),
  })
}));

// Mock AudioEngine
vi.mock('../utils/AudioEngine', () => ({
  default: {
    playClick: vi.fn(),
    isMuted: vi.fn(() => false),
    setMuted: vi.fn(),
  }
}));

describe('Sidebar Component', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders correctly and handles navigation clicks', () => {
    const onNavigateMock = vi.fn();
    render(
      <Sidebar 
        currentRoom="archive" 
        onNavigate={onNavigateMock} 
        onMuteChange={vi.fn()}
        onSearchOpen={vi.fn()}
        onSettingsOpen={vi.fn()}
      />
    );

    // Sidebar navigation should render all 5 rooms
    const mapBtn = screen.getByRole('button', { name: /map/i });
    expect(mapBtn).toBeInTheDocument();

    fireEvent.click(mapBtn);
    expect(onNavigateMock).toHaveBeenCalledWith('map');
  });

  it('toggles mute option when clicking sound button', () => {
    const onMuteChangeMock = vi.fn();
    render(
      <Sidebar 
        currentRoom="archive" 
        onNavigate={vi.fn()} 
        onMuteChange={onMuteChangeMock}
        onSearchOpen={vi.fn()}
        onSettingsOpen={vi.fn()}
      />
    );

    const soundBtn = screen.getByRole('button', { name: /Mute audio/i });
    expect(soundBtn).toBeInTheDocument();

    fireEvent.click(soundBtn);
    expect(onMuteChangeMock).toHaveBeenCalledWith(true);
  });

  it('toggles search overlay and settings panel clicks', () => {
    const onSearchOpenMock = vi.fn();
    const onSettingsOpenMock = vi.fn();

    render(
      <Sidebar 
        currentRoom="archive" 
        onNavigate={vi.fn()} 
        onMuteChange={vi.fn()}
        onSearchOpen={onSearchOpenMock}
        onSettingsOpen={onSettingsOpenMock}
      />
    );

    const searchBtn = screen.getByRole('button', { name: /Search \(Cmd\+K\)/i });
    fireEvent.click(searchBtn);
    expect(onSearchOpenMock).toHaveBeenCalled();

    // Click profile avatar to show menu dropdown
    const avatarBtn = screen.getByRole('button', { name: /Profile menu/i });
    fireEvent.click(avatarBtn);

    // Click Settings menu item inside dropdown
    const settingsBtn = screen.getByRole('menuitem', { name: /Settings/i });
    fireEvent.click(settingsBtn);
    expect(onSettingsOpenMock).toHaveBeenCalled();
  });
});
