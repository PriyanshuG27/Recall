import React from 'react';
import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock window.open
window.open = vi.fn();

// Mock fetch globally
window.fetch = vi.fn();

// Mock alert
window.alert = vi.fn();

// Mock IntersectionObserver
class MockIntersectionObserver {
  constructor(callback) {
    this.callback = callback;
  }
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
window.IntersectionObserver = MockIntersectionObserver;

// Mock @phosphor-icons/react to avoid EMFILE (too many open files) on Windows
vi.mock('@phosphor-icons/react', () => {
  const React = require('react');
  const makeMock = (name) => {
    return function MockIcon(props) {
      return React.createElement('span', { 'data-testid': `icon-${name}`, ...props }, name);
    };
  };
  return {
    MagnifyingGlass: makeMock('MagnifyingGlass'),
    GoogleLogo: makeMock('GoogleLogo'),
    CloudX: makeMock('CloudX'),
    SignOut: makeMock('SignOut'),
    CaretDown: makeMock('CaretDown'),
    CaretUp: makeMock('CaretUp'),
    ShareNetwork: makeMock('ShareNetwork'),
    List: makeMock('List'),
    Link: makeMock('Link'),
    Microphone: makeMock('Microphone'),
    FilePdf: makeMock('FilePdf'),
    Image: makeMock('Image'),
    Note: makeMock('Note'),
    DotsThree: makeMock('DotsThree'),
    Trash: makeMock('Trash'),
    Eye: makeMock('Eye'),
    PaperPlane: makeMock('PaperPlane'),
    Binoculars: makeMock('Binoculars'),
    CheckCircle: makeMock('CheckCircle'),
    XCircle: makeMock('XCircle'),
    Info: makeMock('Info'),
    Warning: makeMock('Warning'),
    Gear: makeMock('Gear')
  };
});

// Mock WebSocket globally to prevent ReferenceError in testing environments
class MockWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    setTimeout(() => {
      this.readyState = 1;
      if (this.onopen) this.onopen();
    }, 0);
  }
  send = vi.fn();
  close = vi.fn();
}
window.WebSocket = MockWebSocket;

// Mock Telegram WebApp SDK globally
window.Telegram = {
  WebApp: {
    ready: vi.fn(),
    expand: vi.fn(),
    viewportStableHeight: 600,
    BackButton: {
      show: vi.fn(),
      hide: vi.fn(),
      onClick: vi.fn(),
      offClick: vi.fn(),
    },
    MainButton: {
      hide: vi.fn(),
    }
  }
};





