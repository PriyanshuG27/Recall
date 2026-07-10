import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import { useAuth } from './AuthContext';
import { useToast } from '../components/Toast';
import client from '../api/client';

export const SocketContext = createContext(null);

export function SocketProvider({ children }) {
  const { user, token, checkAuth } = useAuth();
  const { addToast } = useToast();
  
  const [connectionStatus, setConnectionStatus] = useState('disconnected'); // 'connected' | 'connecting' | 'disconnected' | 'error' | 'failed'
  const [lastSyncTime, setLastSyncTime] = useState(Date.now());
  
  const socketRef = useRef(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimeoutRef = useRef(null);
  const isFailedRef = useRef(false);

  const updateLastSync = () => {
    setLastSyncTime(Date.now());
  };

  const connect = () => {
    if (!user || isFailedRef.current) return;
    if (!navigator.onLine) {
      setConnectionStatus('disconnected');
      return;
    }

    try {
      let base = import.meta.env.VITE_API_URL || '';
      if (!base) {
        const isHttps = window.location.protocol === 'https:';
        base = `${isHttps ? 'wss:' : 'ws:'}//${window.location.host}`;
      } else {
        if (base.startsWith('https://')) {
          base = base.replace('https://', 'wss://');
        } else if (base.startsWith('http://')) {
          base = base.replace('http://', 'ws://');
        } else {
          const isHttps = window.location.protocol === 'https:';
          base = `${isHttps ? 'wss:' : 'ws:'}//${base}`;
        }
      }
      const wsUrl = `${base.replace(/\/$/, '')}/api/ws${token ? `/${token}` : ''}`;
      
      // Prevent duplicate connection attempts if already open/connecting
      if (socketRef.current && (socketRef.current.readyState === WebSocket.OPEN || socketRef.current.readyState === WebSocket.CONNECTING)) {
        return;
      }

      setConnectionStatus('connecting');

      const socket = new WebSocket(wsUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        if (socketRef.current !== socket) return;
        setConnectionStatus('connected');
        reconnectCountRef.current = 0;
        updateLastSync();
      };

      socket.onmessage = (event) => {
        if (socketRef.current !== socket) return;
        updateLastSync();
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'new_node') {
            addToast(`✓ Saved ${data.source_type}!`, 'success');
            window.dispatchEvent(new CustomEvent('online-refetch'));
          } else if (data.type === 'google_connected') {
            addToast('Google Drive connected!', 'success');
            if (checkAuth) checkAuth();
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      socket.onerror = () => {
        if (socketRef.current !== socket) return;
        setConnectionStatus('error');
      };

      socket.onclose = (event) => {
        if (socketRef.current !== socket) return;
        socketRef.current = null;
        if (isFailedRef.current) return;

        setConnectionStatus('disconnected');

        // Do not reconnect if closed normally (1000) or unauthorized (4001)
        if (event && (event.code === 1000 || event.code === 4001)) {
          return;
        }

        if (navigator.onLine) {
          if (reconnectCountRef.current < 5) {
            const backoff = Math.pow(2, reconnectCountRef.current) * 1000; // 1s, 2s, 4s, 8s, 16s
            reconnectCountRef.current += 1;
            
            reconnectTimeoutRef.current = setTimeout(() => {
              connect();
            }, backoff);
          } else {
            isFailedRef.current = true;
            setConnectionStatus('failed');
            addToast('Real-time updates unavailable. Refresh to retry.', 'error');
          }
        }
      };

    } catch (err) {
      console.error('WebSocket connection initialization failed:', err);
      setConnectionStatus('error');
    }
  };

  // Connect when user is present, disconnect when user logs out
  useEffect(() => {
    if (user) {
      isFailedRef.current = false;
      reconnectCountRef.current = 0;
      connect();
    } else {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
      setConnectionStatus('disconnected');
    }

    return () => {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [user]);

  // Intercept window.fetch and axios client responses to update lastSyncTime
  useEffect(() => {
    const handleApiResponse = () => {
      updateLastSync();
    };

    window.addEventListener('api-response-received', handleApiResponse);

    // Global fetch wrapper
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
      try {
        const response = await originalFetch(...args);
        window.dispatchEvent(new CustomEvent('api-response-received'));
        return response;
      } catch (err) {
        window.dispatchEvent(new CustomEvent('api-response-received'));
        throw err;
      }
    };

    // Axios client interceptor
    const responseInterceptor = client.interceptors.response.use(
      (response) => {
        window.dispatchEvent(new CustomEvent('api-response-received'));
        return response;
      },
      (error) => {
        window.dispatchEvent(new CustomEvent('api-response-received'));
        return Promise.reject(error);
      }
    );

    const handleOnline = () => {
      if (isFailedRef.current) return;
      if (!socketRef.current || socketRef.current.readyState === WebSocket.CLOSED) {
        connect();
      }
    };

    window.addEventListener('online', handleOnline);

    return () => {
      window.removeEventListener('api-response-received', handleApiResponse);
      window.removeEventListener('online', handleOnline);
      window.fetch = originalFetch;
      client.interceptors.response.eject(responseInterceptor);
    };
  }, []);

  const providerValue = React.useMemo(() => ({ connectionStatus, lastSyncTime }), [connectionStatus, lastSyncTime]);

  return (
    <SocketContext.Provider value={providerValue}>
      {children}
    </SocketContext.Provider>
  );
}

export function useGraphSocket() {
  const context = useContext(SocketContext);
  if (!context) {
    throw new Error('useGraphSocket must be used within a SocketProvider');
  }
  return context;
}
