import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  // Fetch current user status on mount
  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      // Check for tgWebAppStartParam in query or hash parameters
      const searchParams = new URLSearchParams(window.location.search);
      const startParam = searchParams.get('tgWebAppStartParam') || 
                         window.location.hash.match(/tgWebAppStartParam=([^&]+)/)?.[1];
      if (startParam) {
        // Dev/test environment mock login bypass
        const loginRes = await fetch(`/auth/telegram?id=12345&mock=true`);
        if (loginRes.ok) {
          // Remove from search query or hash to clean up the URL
          if (searchParams.has('tgWebAppStartParam')) {
            searchParams.delete('tgWebAppStartParam');
            const newSearch = searchParams.toString();
            window.history.replaceState(null, null, window.location.pathname + (newSearch ? `?${newSearch}` : ''));
          } else {
            window.history.replaceState(null, null, window.location.pathname);
          }
        }
      }

      const res = await fetch('/auth/me');
      if (res.ok) {
        const data = await res.json();
        setUser({ id: data.id, chat_id: data.chat_id, drive_connected: data.drive_connected, google_last_sync: data.google_last_sync });
        setToken(data.token || null);
      } else {
        setUser(null);
        setToken(null);
      }
    } catch (err) {
      console.error('Authentication check failed:', err);
      setUser(null);
      setToken(null);
    } finally {
      setLoading(false);
    }
  };

  const login = (userData) => {
    setUser(userData);
    if (userData && userData.token) {
      setToken(userData.token);
    }
  };

  const logout = async () => {
    try {
      await fetch('/auth/logout', { method: 'POST' });
    } catch (err) {
      console.error('Logout request failed:', err);
    } finally {
      // NON-NEGOTIABLE SECURITY RULE: Clear all local storage/cache to prevent data leakage
      localStorage.clear();
      sessionStorage.clear();
      setUser(null);
      setToken(null);
    }
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
