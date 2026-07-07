import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/Toast';
import { useGraphSocket as useLegacySocket } from '../context/SocketContext';

export function useGraphSocket(token, initialGraph) {
  // If no token is provided, fall back to the legacy socket context connection status
  const legacyContext = token ? null : useLegacySocket();
  if (!token) {
    return legacyContext;
  }

  const { checkAuth } = useAuth();
  const { addToast } = useToast();

  // Local graph states
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [hubs, setHubs] = useState([]);
  
  // Connection states
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [lastSyncTime, setLastSyncTime] = useState(Date.now());

  const socketRef = useRef(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimeoutRef = useRef(null);
  const pulseTimersRef = useRef({});
  const isFailedRef = useRef(false);

  // Sync state if initialGraph changes
  useEffect(() => {
    if (initialGraph) {
      setNodes(initialGraph.nodes || []);
      setEdges(initialGraph.edges || []);
      setHubs(initialGraph.hubs || []);
    }
  }, [initialGraph]);

  // Clean up all timers on unmount
  useEffect(() => {
    return () => {
      if (socketRef.current) {
        socketRef.current.close(1000);
        socketRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      Object.values(pulseTimersRef.current).forEach(clearTimeout);
      pulseTimersRef.current = {};
    };
  }, []);

  // Connect function
  useEffect(() => {
    isFailedRef.current = false;
    reconnectCountRef.current = 0;
    
    const connect = () => {
      if (isFailedRef.current) return;
      
      // Determine WebSocket URL
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
      const wsUrl = `${base.replace(/\/$/, '')}/api/ws/${token}`;

      // Prevent duplicate connection attempts if already open or connecting
      if (
        socketRef.current &&
        (socketRef.current.readyState === WebSocket.OPEN ||
          socketRef.current.readyState === WebSocket.CONNECTING)
      ) {
        return;
      }

      setConnectionStatus('connecting');
      const socket = new WebSocket(wsUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        if (socketRef.current !== socket) return;
        setConnectionStatus('connected');
        setLastSyncTime(Date.now());
        reconnectCountRef.current = 0;
      };

      socket.onmessage = (event) => {
        if (socketRef.current !== socket) return;
        setLastSyncTime(Date.now());

        try {
          const data = JSON.parse(event.data);

          if (data.type === 'ping') {
            socket.send(JSON.stringify({ type: 'pong' }));
          } else if (data.type === 'new_node' && data.node) {
            const newNode = {
              ...data.node,
              type: 'pulse',
              created_at: data.node.created_at || new Date().toISOString(),
            };

            addToast(`✓ Saved ${data.node.title}!`, 'success');

            setNodes((prevNodes) => {
              if (prevNodes.some((n) => String(n.id) === String(newNode.id))) {
                return prevNodes;
              }
              return [...prevNodes, newNode];
            });

            // Dispatch refetch to keep other UI elements in sync
            window.dispatchEvent(new CustomEvent('online-refetch'));

            // Remove pulse styling after 5 minutes
            if (pulseTimersRef.current[newNode.id]) {
              clearTimeout(pulseTimersRef.current[newNode.id]);
            }
            pulseTimersRef.current[newNode.id] = setTimeout(() => {
              setNodes((prevNodes) =>
                prevNodes.map((n) =>
                  String(n.id) === String(newNode.id)
                    ? { ...n, type: undefined }
                    : n
                )
              );
              delete pulseTimersRef.current[newNode.id];
            }, 5 * 60 * 1000);

          } else if (data.type === 'hubs_updated') {
            const enrichedHubs = (data.hubs || []).map((h) => ({
              ...h,
              updated_at: Date.now(),
            }));
            setHubs(enrichedHubs);
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

        // Reconnect with exponential backoff up to 5 times
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
      };
    };

    connect();

    return () => {
      if (socketRef.current) {
        socketRef.current.close(1000);
        socketRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [token]);

  return {
    nodes,
    edges,
    hubs,
    connectionStatus,
    lastSyncTime,
  };
}
