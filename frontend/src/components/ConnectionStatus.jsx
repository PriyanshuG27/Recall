import React, { useEffect, useState } from 'react';
import { useGraphSocket } from '../hooks/useGraphSocket';

function formatLastUpdated(timestamp) {
  const seconds = Math.floor((Date.now() - timestamp) / 1000);
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes === 1) return '1 minute ago';
  return `${minutes} minutes ago`;
}

export default function ConnectionStatus() {
  const { connectionStatus, lastSyncTime } = useGraphSocket();
  const [relativeTime, setRelativeTime] = useState(formatLastUpdated(lastSyncTime));

  useEffect(() => {
    setRelativeTime(formatLastUpdated(lastSyncTime));

    const interval = setInterval(() => {
      setRelativeTime(formatLastUpdated(lastSyncTime));
    }, 30000);

    return () => clearInterval(interval);
  }, [lastSyncTime]);

  const getStatusDetails = () => {
    switch (connectionStatus) {
      case 'connected':
        return {
          color: 'var(--color-accent, #00D4AA)',
          tooltip: 'Connected',
          className: 'dot-connected'
        };
      case 'connecting':
        return {
          color: '#F59E0B', // Amber
          tooltip: 'Connecting...',
          className: 'dot-connecting'
        };
      case 'error':
        return {
          color: '#EF4444', // Red
          tooltip: 'Connection error',
          className: 'dot-error'
        };
      case 'failed':
        return {
          color: '#EF4444', // Red
          tooltip: 'Connection failed. Refresh to retry.',
          className: 'dot-failed'
        };
      case 'disconnected':
      default:
        return {
          color: '#EF4444', // Red
          tooltip: 'Reconnecting...',
          className: 'dot-disconnected'
        };
    }
  };

  const { color, tooltip, className } = getStatusDetails();

  return (
    <div 
      className="connection-status-container"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        marginRight: '1rem',
        userSelect: 'none'
      }}
      title={tooltip}
    >
      <style>{`
        @keyframes pulse-dot {
          0% {
            transform: scale(0.95);
            box-shadow: 0 0 0 0 rgba(0, 212, 170, 0.7);
          }
          70% {
            transform: scale(1);
            box-shadow: 0 0 0 6px rgba(0, 212, 170, 0);
          }
          100% {
            transform: scale(0.95);
            box-shadow: 0 0 0 0 rgba(0, 212, 170, 0);
          }
        }
        @keyframes spin-dot {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        .dot-connected {
          animation: pulse-dot 2s infinite;
        }
        .dot-connecting {
          animation: spin-dot 1.5s linear infinite;
          border-style: dashed !important;
        }
      `}</style>

      {/* Indicator Dot */}
      <div 
        className={`status-dot ${className}`}
        style={{
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          backgroundColor: color,
          border: connectionStatus === 'connecting' ? `2px solid ${color}` : 'none',
          background: connectionStatus === 'connecting' ? 'transparent' : color,
          boxSizing: 'border-box',
          transition: 'background-color 0.3s ease'
        }}
      />

      {/* Relative Time Timestamp */}
      <span
        style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: '11px',
          color: 'var(--text-tertiary, #8e8e9f)',
          whiteSpace: 'nowrap'
        }}
      >
        Last updated: {relativeTime}
      </span>
    </div>
  );
}
