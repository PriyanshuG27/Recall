import React, { useEffect } from 'react';
import { useAuth } from './context/AuthContext';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import { useToast } from './components/Toast';
import { setToastHandler, setUnauthorizedHandler } from './api/client';

function App() {
  const { user, loading, logout } = useAuth();
  const { addToast, removeToast } = useToast();

  // Register Axios client callbacks to interface with Auth and Toast Contexts
  useEffect(() => {
    setToastHandler(addToast);
    setUnauthorizedHandler(() => {
      logout();
    });
    return () => {
      setToastHandler(null);
      setUnauthorizedHandler(null);
    };
  }, [addToast, logout]);

  // PWA session tracking & installation prompt logic
  useEffect(() => {
    // 1. Session tracking (increment visits if new session)
    const isSessionActive = sessionStorage.getItem('recall_session_active');
    if (!isSessionActive) {
      sessionStorage.setItem('recall_session_active', 'true');
      const currentVisits = parseInt(localStorage.getItem('recall_visits') || '0', 10);
      localStorage.setItem('recall_visits', (currentVisits + 1).toString());
    }

    // 2. Capture beforeinstallprompt event
    let deferredPrompt = null;
    let installToastId = null;

    const handleBeforeInstallPrompt = (e) => {
      e.preventDefault();
      deferredPrompt = e;

      const visits = parseInt(localStorage.getItem('recall_visits') || '0', 10);
      if (visits >= 3) {
        const handleInstallClick = async () => {
          if (!deferredPrompt) return;
          deferredPrompt.prompt();
          const { outcome } = await deferredPrompt.userChoice;
          console.log(`PWA install user outcome: ${outcome}`);
          deferredPrompt = null;
          if (installToastId) {
            removeToast(installToastId);
          }
        };

        installToastId = addToast(
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', justifyContent: 'space-between', width: '100%' }}>
            <span>Add Recall to your homescreen?</span>
            <button
              onClick={handleInstallClick}
              className="btn"
              style={{
                padding: '0.25rem 0.75rem',
                fontSize: '0.75rem',
                minHeight: '28px',
                backgroundColor: 'var(--color-secondary)',
                color: '#000',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 'bold'
              }}
            >
              Install
            </button>
          </div>,
          'info',
          { persistent: true }
        );
      }
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      if (installToastId) {
        removeToast(installToastId);
      }
    };
  }, [addToast, removeToast]);

  // Online/Offline detection with toast alerts and data refetches
  useEffect(() => {
    let offlineToastId = null;

    const handleOffline = () => {
      if (!offlineToastId) {
        offlineToastId = addToast("You're offline", 'error', { persistent: true });
      }
    };

    const handleOnline = () => {
      if (offlineToastId) {
        removeToast(offlineToastId);
        offlineToastId = null;
      }
      window.dispatchEvent(new Event('online-refetch'));
    };

    window.addEventListener('offline', handleOffline);
    window.addEventListener('online', handleOnline);

    if (!navigator.onLine) {
      handleOffline();
    }

    return () => {
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('online', handleOnline);
      if (offlineToastId) {
        removeToast(offlineToastId);
      }
    };
  }, [addToast, removeToast]);

  useEffect(() => {
    if (!user) return;

    let socket;
    let reconnectTimeout;
    let didError = false;

    function connect() {
      if (!navigator.onLine) return;

      try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/ws`;
        socket = new WebSocket(wsUrl);

        socket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'new_node') {
              addToast(`✓ Saved ${data.source_type}!`, 'success');
            } else if (data.type === 'google_connected') {
              addToast('Google Drive connected!', 'success');
            }
          } catch (err) {
            console.error('Failed to parse WebSocket message:', err);
          }
        };

        socket.onerror = () => {
          if (navigator.onLine && !didError) {
            addToast('Connection error — retrying...', 'error');
            didError = true;
          }
        };

        socket.onclose = () => {
          if (navigator.onLine) {
            reconnectTimeout = setTimeout(() => {
              connect();
            }, 3000);
          }
        };

        socket.onopen = () => {
          didError = false;
        };
      } catch (err) {
        console.error('WebSocket connection failed:', err);
      }
    }

    const handleOnline = () => {
      if (!socket || socket.readyState === WebSocket.CLOSED) {
        connect();
      }
    };

    window.addEventListener('online', handleOnline);

    connect();

    return () => {
      window.removeEventListener('online', handleOnline);
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
      clearTimeout(reconnectTimeout);
    };
  }, [user, addToast]);

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', backgroundColor: 'var(--bg-deep)', color: 'var(--color-text)' }}>
        <h2 className="gradient-text">Recall</h2>
        <p style={{ marginTop: '0.5rem', color: 'var(--color-text-muted)' }}>Verifying secure session...</p>
      </div>
    );
  }

  return (
    <div style={{ position: 'relative', minHeight: '100vh', backgroundColor: 'var(--bg-deep)' }}>
      <div className="nebula-blob nebula-violet"></div>
      <div className="nebula-blob nebula-mint"></div>
      {!user ? (
        <div style={{ position: 'relative', zIndex: 1 }}>
          <Login />
        </div>
      ) : (
        <div style={{ position: 'relative', zIndex: 1 }}>
          <Dashboard />
        </div>
      )}
    </div>
  );
}

export default App;
