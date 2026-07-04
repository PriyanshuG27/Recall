import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import RoomTransition from '../components/RoomTransition';

describe('RoomTransition Component', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders children immediately if there is no room change', () => {
    render(
      <RoomTransition fromRoom="archive" toRoom="archive" onDone={vi.fn()}>
        <div data-testid="room-content">New Content</div>
      </RoomTransition>
    );

    expect(screen.getByTestId('room-content')).toBeInTheDocument();
  });

  it('renders slam overlay and reveals new content on room change', async () => {
    const onDoneMock = vi.fn();
    render(
      <RoomTransition fromRoom="archive" toRoom="map" onDone={onDoneMock}>
        <div data-testid="room-content">New Content</div>
      </RoomTransition>
    );

    // Run timeout to trigger gsap timeline onComplete callback
    await act(async () => {
      vi.runAllTimers();
    });

    expect(onDoneMock).toHaveBeenCalled();
    expect(screen.getByTestId('room-content')).toBeInTheDocument();
  });
});
