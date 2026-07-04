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
  return new Proxy({}, {
    get: (target, name) => {
      if (
        name === 'then' || 
        name === '__esModule' || 
        name === 'default' || 
        typeof name === 'symbol'
      ) {
        return undefined;
      }
      return function MockIcon(props) {
        return React.createElement('span', { 'data-testid': `icon-${name}`, ...props }, name);
      };
    },
    has: (target, name) => {
      if (
        name === 'then' || 
        name === '__esModule' || 
        name === 'default' || 
        typeof name === 'symbol'
      ) {
        return false;
      }
      return true;
    },
    getOwnPropertyDescriptor: (target, name) => {
      if (
        name === 'then' || 
        name === '__esModule' || 
        name === 'default' || 
        typeof name === 'symbol'
      ) {
        return undefined;
      }
      return {
        enumerable: true,
        configurable: true,
        writable: true,
        value: function MockIcon(props) {
          return React.createElement('span', { 'data-testid': `icon-${name}`, ...props }, name);
        }
      };
    }
  });
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
  arcTo: vi.fn(),
  fill: vi.fn(),
  closePath: vi.fn(),
  lineTo: vi.fn(),
  createRadialGradient: vi.fn(() => ({
    addColorStop: vi.fn()
  })),
  createLinearGradient: vi.fn(() => ({
    addColorStop: vi.fn()
  })),
  fillText: vi.fn(),
  fillRect: vi.fn(),
  measureText: vi.fn(() => ({ width: 100 })),
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
    Html: ({ children }) => React.createElement('div', { 'data-testid': 'r3f-html' }, children),
    OrbitControls: () => React.createElement('div', { 'data-testid': 'r3f-orbitcontrols' }),
    Line: () => React.createElement('div', { 'data-testid': 'r3f-line' })
  };
});

// Mock ResizeObserver globally for JSDOM
class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = MockResizeObserver;

window.URL.createObjectURL = vi.fn();
window.URL.revokeObjectURL = vi.fn();

// Global GSAP Mock with regular functions to prevent vi.restoreAllMocks reset failures
const tlMock = {
  fromTo: function() { return this; },
  to: function() { return this; },
  kill: function() { return this; },
};

vi.mock('gsap', () => {
  return {
    default: {
      timeline: (config) => {
        if (config && config.onComplete) {
          setTimeout(() => config.onComplete(), 0);
        }
        return tlMock;
      },
      fromTo: () => tlMock,
      to: () => tlMock,
    }
  };
});



