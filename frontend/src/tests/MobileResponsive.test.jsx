import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import Dashboard from '../pages/Dashboard';
import { AuthProvider, useAuth } from '../context/AuthContext';
import { ToastProvider } from '../components/Toast';

// Helper component to seed context
function SeedAuth({ user, children }) {
  const { login } = useAuth();
  React.useEffect(() => {
    if (user) login(user);
  }, [user]);
  return children;
}

describe('Mobile Responsive Layouts and Gestures', () => {
  let originalInnerWidth;
  let fetchSpy;

  const setWidth = (width) => {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: width,
    });
    window.dispatchEvent(new Event('resize'));
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();

    originalInnerWidth = window.innerWidth;

    fetchSpy = vi.spyOn(window, 'fetch').mockImplementation((url) => {
      if (url === '/auth/me') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ id: 42, chat_id: '12345' }),
        });
      }
      if (url === '/api/quizzes/due') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([]),
        });
      }
      if (url.includes('/api/items')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            items: [
              { id: 1, title: 'Machine Learning', summary: 'AI and neural networks', source_type: 'url', source_url: 'https://example.com/ml', tags: ['ml'], created_at: '2026-06-26' },
              { id: 2, title: 'Transformers', summary: 'Attention is all you need', source_type: 'url', source_url: 'https://example.com/transformers', tags: ['transformers'], created_at: '2026-06-26' }
            ],
            total: 2,
            pages: 1
          }),
        });
      }
      if (url.includes('/api/graph')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            nodes: [
              { id: 1, title: 'Machine Learning', source_type: 'url', created_at: '2026-06-26', is_hub: true },
              { id: 2, title: 'Transformers', source_type: 'url', created_at: '2026-06-26', is_hub: false }
            ],
            edges: [
              { source: 1, target: 2, weight: 0.85 }
            ],
            hubs: [
              { id: 1, label: 'AI Guides', member_ids: [1] }
            ]
          }),
        });
      }
      return Promise.resolve({ ok: false });
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: originalInnerWidth,
    });
  });

  it('binds Telegram WebApp ready and expand on mount', async () => {
    render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, chat_id: '12345' }}>
            <Dashboard />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(window.Telegram.WebApp.ready).toHaveBeenCalled();
      expect(window.Telegram.WebApp.expand).toHaveBeenCalled();
    });
  });

  it('toggles Header search bar expansion on mobile layout', async () => {
    setWidth(375); // Mobile width

    render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, chat_id: '12345' }}>
            <Dashboard />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    // Get search container which should be in header
    await waitFor(() => {
      expect(screen.getByPlaceholderText('Search your brain...')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Search your brain...');
    const searchContainer = searchInput.closest('.search-bar-container');

    expect(searchContainer).toBeInTheDocument();
    expect(searchContainer).not.toHaveClass('expanded');

    // Click/tap the container to expand search
    fireEvent.click(searchContainer);
    expect(searchContainer).toHaveClass('expanded');

    // Focus input and then blur it to collapse
    fireEvent.blur(searchInput);
    expect(searchContainer).not.toHaveClass('expanded');
  });

  it('triggers Telegram BackButton actions and panel closure when node is selected', async () => {
    render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, chat_id: '12345' }}>
            <Dashboard />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Machine Learning')).toBeInTheDocument();
    });

    const mlNode = screen.getByText('Machine Learning').closest('.constellation-node');

    // Click the node
    fireEvent.click(mlNode);

    // BackButton should be shown
    expect(window.Telegram.WebApp.BackButton.show).toHaveBeenCalled();
    expect(window.Telegram.WebApp.BackButton.onClick).toHaveBeenCalled();

    // Verify detail panel opens
    await waitFor(() => {
      expect(screen.getByText('AI and neural networks')).toBeInTheDocument();
    });

    // Call back button click handler
    const backBtnHandler = window.Telegram.WebApp.BackButton.onClick.mock.calls[0][0];
    backBtnHandler();

    // Verify detail panel closes and BackButton offClick/hide are called
    await waitFor(() => {
      expect(screen.queryByText('AI and neural networks')).not.toBeInTheDocument();
    });
  });

  it('handles canvas touch panning', async () => {
    const { container } = render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, chat_id: '12345' }}>
            <Dashboard />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Machine Learning')).toBeInTheDocument();
    });

    const canvas = container.querySelector('.graph-canvas-container');
    const inner = container.querySelector('.graph-canvas-inner');

    expect(canvas).toBeInTheDocument();
    expect(inner).toBeInTheDocument();

    // Initial transform style check
    expect(inner.style.transform).toContain('translate(0px, 0px) scale(1)');

    // Start touch pan
    fireEvent.touchStart(canvas, {
      touches: [{ clientX: 100, clientY: 100 }]
    });

    // Move touch pan
    fireEvent.touchMove(canvas, {
      touches: [{ clientX: 150, clientY: 120 }]
    });

    // End touch pan
    fireEvent.touchEnd(canvas, {
      changedTouches: [{ clientX: 150, clientY: 120 }]
    });

    // Verify inner canvas transform updated
    expect(inner.style.transform).toContain('translate(50px, 20px)');
  });

  it('handles canvas touch pinch-zoom', async () => {
    const { container } = render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, chat_id: '12345' }}>
            <Dashboard />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Machine Learning')).toBeInTheDocument();
    });

    const canvas = container.querySelector('.graph-canvas-container');
    const inner = container.querySelector('.graph-canvas-inner');

    // Start pinch zoom with 2 touches (distance = 100)
    fireEvent.touchStart(canvas, {
      touches: [
        { clientX: 100, clientY: 100 },
        { clientX: 200, clientY: 100 }
      ]
    });

    // Move pinch zoom out (distance = 200, scale ratio = 2)
    fireEvent.touchMove(canvas, {
      touches: [
        { clientX: 50, clientY: 100 },
        { clientX: 250, clientY: 100 }
      ]
    });

    // End touch zoom
    fireEvent.touchEnd(canvas);

    // Verify scale increased
    expect(inner.style.transform).toContain('scale(2)');
  });

  it('triggers context menu on node long-press', async () => {
    const { container } = render(
      <ToastProvider>
        <AuthProvider>
          <SeedAuth user={{ id: 42, chat_id: '12345' }}>
            <Dashboard />
          </SeedAuth>
        </AuthProvider>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Machine Learning')).toBeInTheDocument();
    });

    const mlNode = screen.getByText('Machine Learning').closest('.constellation-node');

    // Start fake timers just for testing the long press setTimeout duration
    vi.useFakeTimers();

    // Start mousedown/touchstart on the node
    fireEvent.mouseDown(mlNode, { clientX: 100, clientY: 100, button: 0 });

    // Advance timer by 500ms
    vi.advanceTimersByTime(500);

    // Restore real timers so that React Testing Library's async waitFor works correctly
    vi.useRealTimers();

    // Context menu should now be visible
    await waitFor(() => {
      expect(screen.getByText('View source')).toBeInTheDocument();
      expect(screen.getByText('Delete item')).toBeInTheDocument();
    });

    // Clicking "View source" should trigger toast or window.open
    const viewSourceBtn = screen.getByText('View source');
    fireEvent.click(viewSourceBtn);

    // Menu should close
    await waitFor(() => {
      expect(screen.queryByText('View source')).not.toBeInTheDocument();
    });
  });
});
