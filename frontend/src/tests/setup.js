import React from 'react';
import '@testing-library/jest-dom';
import { vi, beforeEach } from 'vitest';

beforeEach(() => {
  vi.useRealTimers();
});

// Mock window.open
window.open = vi.fn();

// Mock fetch globally
window.fetch = vi.fn();

// Mock alert
window.alert = vi.fn();

// Mock matchMedia globally
window.matchMedia = window.matchMedia || function() {
  return {
    matches: false,
    addListener: function() {},
    removeListener: function() {},
    addEventListener: function() {},
    removeEventListener: function() {}
  };
};

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

vi.mock('@phosphor-icons/react', () => {
  const React = require('react');
  const makeMock = (name) => {
    return function MockIcon(props) {
      return React.createElement('span', { 'data-testid': `icon-${name}`, ...props }, name);
    };
  };
  return {
    SquaresFour: makeMock('SquaresFour'),
    MagnifyingGlass: makeMock('MagnifyingGlass'),
    GoogleLogo: makeMock('GoogleLogo'),
    CloudX: makeMock('CloudX'),
    CloudArrowUp: makeMock('CloudArrowUp'),
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
    Gear: makeMock('Gear'),
    X: makeMock('X'),
    Bell: makeMock('Bell'),
    BookOpen: makeMock('BookOpen'),
    TextT: makeMock('TextT'),
    ChartBar: makeMock('ChartBar'),
    Trophy: makeMock('Trophy'),
    Hourglass: makeMock('Hourglass'),
    Percent: makeMock('Percent'),
    Compass: makeMock('Compass'),
    Flame: makeMock('Flame'),
    User: makeMock('User'),
    Globe: makeMock('Globe'),
    SpeakerHigh: makeMock('SpeakerHigh'),
    SpeakerSlash: makeMock('SpeakerSlash'),
    CalendarPlus: makeMock('CalendarPlus'),
    Plus: makeMock('Plus'),
    Clock: makeMock('Clock'),
    Database: makeMock('Database'),
    Rows: makeMock('Rows'),
    ArrowsInLine: makeMock('ArrowsInLine'),
    ArrowsOutLine: makeMock('ArrowsOutLine'),
    Play: makeMock('Play'),
    Pause: makeMock('Pause'),
    Selection: makeMock('Selection'),
    ArrowsIn: makeMock('ArrowsIn'),
    Crosshair: makeMock('Crosshair'),
    Tag: makeMock('Tag'),
    Activity: makeMock('Activity'),
    Folder: makeMock('Folder'),
    GoogleDriveLogo: makeMock('GoogleDriveLogo'),
    Lightning: makeMock('Lightning'),
    ClockCounterClockwise: makeMock('ClockCounterClockwise'),
    Hash: makeMock('Hash'),
    ArrowSquareOut: makeMock('ArrowSquareOut'),
    CaretRight: makeMock('CaretRight'),
    Sparkle: makeMock('Sparkle'),
    Copy: makeMock('Copy'),
    Check: makeMock('Check'),
    UploadSimple: makeMock('UploadSimple'),
    DownloadSimple: makeMock('DownloadSimple'),
    ArrowRight: makeMock('ArrowRight'),
    BookmarkSimple: makeMock('BookmarkSimple'),
    Lightning: makeMock('Lightning'),
  };
});




// Mock WebSocket globally to prevent ReferenceError in testing environments
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
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
global.WebSocket = MockWebSocket;

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

// Mock Canvas 2D context globally
const mockContext = {
  clearRect: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  translate: vi.fn(),
  scale: vi.fn(),
  beginPath: vi.fn(),
  moveTo: vi.fn(),
  quadraticCurveTo: vi.fn(),
  stroke: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  createRadialGradient: vi.fn(() => ({
    addColorStop: vi.fn()
  })),
  fillText: vi.fn(),
  setLineDash: vi.fn()
};

HTMLCanvasElement.prototype.getContext = vi.fn().mockImplementation((type) => {
  if (type === '2d') return mockContext;
  return null;
});

// Mock useGraphSocket globally
vi.mock('../hooks/useGraphSocket', () => {
  return {
    useGraphSocket: vi.fn(() => ({
      connectionStatus: 'connected',
      lastSyncTime: Date.now(),
    })),
  };
});
vi.mock('@react-three/fiber', () => {
  const React = require('react');
  return {
    Canvas: ({ children }) => React.createElement('div', { 'data-testid': 'r3f-canvas' }, children),
    useFrame: vi.fn(),
    useThree: vi.fn(() => ({
      camera: { position: { x: 0, y: 0, z: 0 }, lookAt: vi.fn() },
      mouse: { x: 0, y: 0 },
      viewport: { width: 100, height: 100 }
    }))
  };
});

vi.mock('@react-three/drei', () => {
  const React = require('react');
  return {
    Html: ({ children }) => React.createElement('div', { 'data-testid': 'r3f-html' }, children)
  };
});

