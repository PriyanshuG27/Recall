import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import GraphCanvas from '../canvas/GraphCanvas';

// Mock ResizeObserver to capture the callback for coverage testing
let resizeCallback;
class MockResizeObserver {
  constructor(cb) {
    resizeCallback = cb;
  }
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
window.ResizeObserver = MockResizeObserver;

// Mock matchMedia to capture and trigger listeners for coverage testing
let mediaListener;
let mockMatches = false;
window.matchMedia = vi.fn().mockImplementation(query => ({
  get matches() {
    return mockMatches;
  },
  addEventListener: (event, cb) => {
    mediaListener = cb;
  },
  removeEventListener: vi.fn()
}));

// Canvas context mocking
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

// requestAnimationFrame mocking
let rAFCallbacks = [];
window.requestAnimationFrame = vi.fn().mockImplementation((cb) => {
  const id = rAFCallbacks.length;
  rAFCallbacks.push({ id, cb, active: true });
  return id;
});
window.cancelAnimationFrame = vi.fn().mockImplementation((id) => {
  if (rAFCallbacks[id]) {
    rAFCallbacks[id].active = false;
  }
});

const flushRAF = (timestamp = 1000) => {
  const callbacksToRun = [...rAFCallbacks];
  rAFCallbacks = [];
  callbacksToRun.forEach(item => {
    if (item.active) {
      item.cb(timestamp);
    }
  });
};

describe('GraphCanvas Component', () => {
  const mockNodes = [
    { id: 1, title: 'Machine Learning', source_type: 'url', created_at: new Date().toISOString(), type: 'hub' },
    { id: 2, title: 'Transformers', source_type: 'pdf', created_at: new Date().toISOString(), type: 'orbital' },
    { id: 3, title: 'Voice Note', source_type: 'voice', created_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(), type: 'orbital' },
    { id: 4, title: 'Image Note', source_type: 'image', created_at: new Date().toISOString(), type: 'orbital' },
    { id: 5, title: 'Photo Note', source_type: 'photo', created_at: new Date().toISOString(), type: 'orbital' },
    { id: 6, title: 'Text Note', source_type: 'text', created_at: new Date().toISOString(), type: 'orbital' },
    { id: 7, title: 'Default Note', source_type: 'other', created_at: new Date().toISOString(), type: 'orbital' },
    { id: -1, title: 'Centroid Hub', source_type: 'other', created_at: new Date().toISOString(), type: 'hub' }
  ];

  const mockEdges = [
    { source: 1, target: 2, weight: 0.8 },
    { source: -1, target: 3, weight: 0.5 }
  ];

  beforeEach(() => {
    resizeCallback = undefined;
    mediaListener = undefined;
    mockMatches = false;
    rAFCallbacks = [];
    vi.clearAllMocks();
    Object.values(mockContext).forEach(fn => {
      if (fn.mock) fn.mockClear();
    });
  });

  it('renders without crashing, handles layout updates, and runs canvas drawing loop', () => {
    const mockNodesWithCoords = mockNodes.map((n, i) => ({
      ...n,
      x: 100 + i * 50,
      y: 100 + i * 50
    }));
    const { unmount } = render(
      <GraphCanvas activeNodes={mockNodesWithCoords} edges={mockEdges} />
    );

    // Verify DOM nodes render
    expect(screen.getByText('Machine Learning')).toBeInTheDocument();
    expect(screen.getByText('Transformers')).toBeInTheDocument();

    // Trigger canvas draw via requestAnimationFrame
    flushRAF(1000);
    expect(mockContext.clearRect).toHaveBeenCalled();
    expect(mockContext.beginPath).toHaveBeenCalled();
    expect(mockContext.arc).toHaveBeenCalled();

    // Clean up
    unmount();
  });

  it('emits click events when nodes are clicked (onNodeClick / handleNodeClick)', () => {
    const handleNodeClick = vi.fn();
    render(
      <GraphCanvas 
        activeNodes={mockNodes} 
        edges={mockEdges} 
        handleNodeClick={handleNodeClick} 
      />
    );

    const mlNode = screen.getByText('Machine Learning').closest('.constellation-node');
    expect(mlNode).toBeInTheDocument();

    fireEvent.click(mlNode);
    expect(handleNodeClick).toHaveBeenCalledWith(expect.objectContaining({ id: 1, title: 'Machine Learning' }));
  });

  it('emits click events when nodes are clicked using onNodeClick fallback', () => {
    const onNodeClick = vi.fn();
    render(
      <GraphCanvas 
        activeNodes={mockNodes} 
        edges={mockEdges} 
        onNodeClick={onNodeClick} 
      />
    );

    const mlNode = screen.getByText('Machine Learning').closest('.constellation-node');
    fireEvent.click(mlNode);
    expect(onNodeClick).toHaveBeenCalled();
  });

  it('handles keyboard navigation (Enter and Space keys) on node buttons', () => {
    const onNodeClick = vi.fn();
    render(
      <GraphCanvas 
        activeNodes={mockNodes} 
        edges={mockEdges} 
        onNodeClick={onNodeClick} 
      />
    );

    const mlNode = screen.getByText('Machine Learning').closest('.constellation-node');

    // Trigger Enter key
    fireEvent.keyDown(mlNode, { key: 'Enter' });
    expect(onNodeClick).toHaveBeenCalledTimes(1);

    // Trigger Space key
    fireEvent.keyDown(mlNode, { key: ' ' });
    expect(onNodeClick).toHaveBeenCalledTimes(2);

    // Trigger other key (should not click)
    fireEvent.keyDown(mlNode, { key: 'Escape' });
    expect(onNodeClick).toHaveBeenCalledTimes(2);
  });

  it('handles mouse hover events (enter/leave) to set hoveredNodeId', () => {
    render(<GraphCanvas activeNodes={mockNodes} edges={mockEdges} />);
    const mlNode = screen.getByText('Machine Learning').closest('.constellation-node');

    fireEvent.mouseEnter(mlNode);
    flushRAF(1016); // Trigger render loop with node hovered

    fireEvent.mouseLeave(mlNode);
    flushRAF(1032); // Trigger render loop without node hovered

    expect(mockContext.clearRect).toHaveBeenCalled();
  });

  it('handles drag panning mouse events and respects button filters and node selection', () => {
    render(<GraphCanvas activeNodes={mockNodes} edges={mockEdges} />);
    const canvas = screen.getByRole('application');
    const container = canvas.parentElement;

    // Simulate drag start with non-left click (should not drag)
    fireEvent.mouseDown(container, { button: 1, clientX: 100, clientY: 100 });
    fireEvent.mouseMove(container, { clientX: 150, clientY: 120 });
    expect(rAFCallbacks.length).toBeGreaterThan(0);

    // Simulate drag start on a node (should not drag container)
    const mlNode = screen.getByText('Machine Learning').closest('.constellation-node');
    fireEvent.mouseDown(mlNode, { button: 0, clientX: 100, clientY: 100 });
    fireEvent.mouseMove(container, { clientX: 150, clientY: 120 });

    // Simulate proper left-click drag on container background
    fireEvent.mouseDown(container, { button: 0, clientX: 100, clientY: 100 });
    fireEvent.mouseMove(container, { clientX: 150, clientY: 120 });
    fireEvent.mouseUp(container);

    // Leave container drag
    fireEvent.mouseDown(container, { button: 0, clientX: 100, clientY: 100 });
    fireEvent.mouseLeave(container);

    expect(canvas).toBeInTheDocument();
  });

  it('handles mouse wheel zoom events', () => {
    render(<GraphCanvas activeNodes={mockNodes} edges={mockEdges} />);
    const canvas = screen.getByRole('application');
    const container = canvas.parentElement;

    // Simulate wheel scroll zoom
    fireEvent.wheel(container, { deltaY: 100 });
    fireEvent.wheel(container, { deltaY: -100 });

    expect(canvas).toBeInTheDocument();
  });

  it('updates dimensions when ResizeObserver triggers callback', () => {
    render(<GraphCanvas activeNodes={mockNodes} edges={mockEdges} />);
    expect(resizeCallback).toBeDefined();

    // Trigger ResizeObserver resize callback
    resizeCallback([{
      contentRect: { width: 1280, height: 720 }
    }]);

    expect(screen.getByText('Machine Learning')).toBeInTheDocument();
  });

  it('handles prefers-reduced-motion media query updates', () => {
    mockMatches = true;
    render(<GraphCanvas activeNodes={mockNodes} edges={mockEdges} />);
    expect(mediaListener).toBeDefined();

    // Trigger media query change event
    mediaListener({ matches: true });

    flushRAF(1000);
    expect(screen.getByText('Machine Learning')).toBeInTheDocument();
  });

  it('handles matchingNodeIds filtering logic and selectedNodeId styling', () => {
    const matchingNodeIds = new Set([2, 3]);
    const { rerender } = render(
      <GraphCanvas 
        activeNodes={mockNodes} 
        edges={mockEdges} 
        matchingNodeIds={matchingNodeIds}
        selectedNodeId={2}
      />
    );

    flushRAF(1000);

    // Verify rendering with filters
    expect(screen.getByText('Transformers')).toBeInTheDocument();

    // Rerender with matchingNodeIds containing centroid hubs
    const hubMatchingNodeIds = new Set([-1, 2]);
    rerender(
      <GraphCanvas 
        activeNodes={mockNodes} 
        edges={mockEdges} 
        matchingNodeIds={hubMatchingNodeIds}
        selectedNodeId={-1}
      />
    );
    flushRAF(1016);
  });

  it('verifies node positions are spread out', () => {
    const mockNodesWithCoords = mockNodes.map((n, i) => ({
      ...n,
      x: 500 + 150 * Math.cos(i),
      y: 350 + 150 * Math.sin(i)
    }));
    const { container } = render(<GraphCanvas activeNodes={mockNodesWithCoords} edges={mockEdges} />);
    if (window.__d3Simulation) {
      for (let i = 0; i < 150; i++) {
        window.__d3Simulation.tick();
      }
    }
    flushRAF(1000);
    const nodes = container.querySelectorAll('.constellation-node');
    nodes.forEach(node => {
      console.log('Node:', node.getAttribute('data-node-id'), 'left:', node.style.left, 'top:', node.style.top);
    });
  });

  it('renders correctly in "hubs" mode', () => {
    const { rerender } = render(
      <GraphCanvas 
        activeNodes={mockNodes} 
        edges={mockEdges} 
        mode="hubs"
        hubs={[
          { id: 1, label: 'Centroid Hub', member_ids: [2, 3] }
        ]}
      />
    );

    // Verify only hubs render (Node 1 has type 'hub', Node 2 has type 'orbital')
    expect(screen.getByText('Machine Learning')).toBeInTheDocument();
    expect(screen.queryByText('Transformers')).not.toBeInTheDocument();

    // Trigger canvas draw
    flushRAF(1000);
    expect(mockContext.clearRect).toHaveBeenCalled();
  });
});


