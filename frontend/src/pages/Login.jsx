import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const { login } = useAuth();
  const [error, setError] = useState('');
  const [customChatId, setCustomChatId] = useState('');

  // Load the live Telegram Login widget
  useEffect(() => {
    const script = document.createElement('script');
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.setAttribute("data-telegram-login", "RecallTestBot");
    script.setAttribute("data-size", "large");
    script.setAttribute("data-auth-url", "/auth/telegram");
    script.setAttribute("data-request-access", "write");
    script.async = true;
    
    const container = document.getElementById('telegram-widget-container');
    if (container) {
      container.appendChild(script);
    }
  }, []);

  const handleDeveloperBypass = async () => {
    try {
      const targetId = customChatId.trim() || '12345';
      const res = await fetch(`/auth/telegram?id=${targetId}&mock=true`);
      if (res.ok) {
        const check = await fetch('/auth/me');
        if (check.ok) {
          const profile = await check.json();
          login({ id: profile.id, chat_id: profile.chat_id });
        }
      } else {
        setError('Bypass login failed.');
      }
    } catch (err) {
      console.error(err);
      setError('Connection error.');
    }
  };

  return (
    <div className="page-container">
      <div className="login-card glass-panel">
        <div>
          <h2 className="gradient-text" style={{ fontSize: '2rem' }}>Recall</h2>
          <p style={{ marginTop: '0.25rem' }}>Your personal constellation mind map</p>
        </div>

        {error && (
          <div style={{ color: '#ef4444', fontSize: '0.9rem', backgroundColor: 'rgba(239, 68, 68, 0.1)', padding: '0.5rem', borderRadius: '6px' }}>
            {error}
          </div>
        )}

        <div className="widget-container" id="telegram-widget-container">
          {/* Telegram Login Widget is loaded here */}
        </div>

        <div className="divider">Or Developer Access</div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', width: '100%', marginBottom: '0.75rem' }}>
          <label htmlFor="custom-chat-id" style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)', textAlign: 'left' }}>
            Telegram Chat ID to view your bot items
          </label>
          <input
            id="custom-chat-id"
            type="text"
            value={customChatId}
            onChange={(e) => setCustomChatId(e.target.value)}
            placeholder="e.g. 123456789"
            style={{
              width: '100%',
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid var(--border-glass)',
              color: 'var(--color-text)',
              padding: '0.5rem',
              borderRadius: '6px',
              outline: 'none',
              fontSize: '0.875rem'
            }}
          />
        </div>

        <button className="btn btn-primary" onClick={handleDeveloperBypass}>
          ⚡ Developer Bypass Login
        </button>
      </div>
    </div>
  );
}
