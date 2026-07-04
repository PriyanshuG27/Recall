import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import GraphControls from '../components/GraphControls';

describe('GraphControls Component', () => {
  const mockUser = { username: 'testuser', first_name: 'Test' };

  it('renders pill buttons and handles view mode changes', () => {
    const onViewModeChangeMock = vi.fn();
    render(
      <GraphControls
        viewMode="graph"
        onViewModeChange={onViewModeChangeMock}
        dueQuizCount={3}
        user={mockUser}
        onLogout={vi.fn()}
        onSettingsClick={vi.fn()}
        onSearchOpen={vi.fn()}
      />
    );

    // Verify quiz badge count is present
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('handles avatar dropdown toggle and settings click', () => {
    const onSettingsClickMock = vi.fn();
    const onLogoutMock = vi.fn();

    render(
      <GraphControls
        viewMode="graph"
        onViewModeChange={vi.fn()}
        dueQuizCount={0}
        user={mockUser}
        onLogout={onLogoutMock}
        onSettingsClick={onSettingsClickMock}
        onSearchOpen={vi.fn()}
      />
    );

    const avatarBtn = screen.getByText('T');
    fireEvent.click(avatarBtn);

    const settingsOption = screen.getByText('Settings');
    fireEvent.click(settingsOption);
    expect(onSettingsClickMock).toHaveBeenCalled();
  });

  it('triggers onSearchOpen when "/" key is pressed', () => {
    const onSearchOpenMock = vi.fn();
    render(
      <GraphControls
        viewMode="graph"
        onViewModeChange={vi.fn()}
        dueQuizCount={0}
        user={mockUser}
        onLogout={vi.fn()}
        onSettingsClick={vi.fn()}
        onSearchOpen={onSearchOpenMock}
      />
    );

    fireEvent.keyDown(window, { key: '/' });
    expect(onSearchOpenMock).toHaveBeenCalled();
  });
});
