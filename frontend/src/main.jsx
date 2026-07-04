import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './theme.css';
import './index.css';
import { AuthProvider } from './context/AuthContext.jsx';
import { ToastProvider } from './components/Toast.jsx';
import { SocketProvider } from './context/SocketContext.jsx';
import { initPerformanceMonitor } from './utils/PerformanceMonitor.js';

// Initialize local Web Vitals performance tracing
initPerformanceMonitor();

/* ── Telegram WebApp Fetch Interceptor ──────────────────────── */
if (typeof window !== 'undefined') {
  const originalFetch = window.fetch;
  window.fetch = function (url, options = {}) {
    if (window.Telegram?.WebApp?.initData) {
      options.headers = {
        ...options.headers,
        'Authorization': `TelegramInitData ${window.Telegram.WebApp.initData}`
      };
    }
    return originalFetch(url, options);
  };
}

/* ── Dev-mode error overlay (shows crash message on screen) ── */
class DevErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{
          position: 'fixed', inset: 0, background: '#08070A',
          color: '#F4EFEB', fontFamily: 'monospace', padding: '2rem',
          zIndex: 9999, overflow: 'auto',
        }}>
          <div style={{ color: '#CFA365', fontSize: '1.1rem', fontWeight: 700, marginBottom: '1rem' }}>
            ⚡ Recall — Render Error
          </div>
          <div style={{ color: '#e07070', fontSize: '0.9rem', marginBottom: '1rem', whiteSpace: 'pre-wrap' }}>
            {this.state.error.message}
          </div>
          <div style={{ color: '#8E8985', fontSize: '0.75rem', whiteSpace: 'pre-wrap' }}>
            {this.state.error.stack}
          </div>
          <button
            onClick={() => window.location.reload()}
            style={{ marginTop: '1.5rem', padding: '0.5rem 1rem', background: '#CFA365', color: '#08070A', border: 'none', borderRadius: 4, cursor: 'pointer', fontFamily: 'monospace', fontWeight: 700 }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <DevErrorBoundary>
      <AuthProvider>
        <ToastProvider>
          <SocketProvider>
            <App />
          </SocketProvider>
        </ToastProvider>
      </AuthProvider>
    </DevErrorBoundary>
  </React.StrictMode>,
);
