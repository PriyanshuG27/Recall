import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { CheckCircle, XCircle, Info, Warning } from '@phosphor-icons/react';

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const toastsRef = React.useRef([]);

  useEffect(() => {
    toastsRef.current = toasts;
  }, [toasts]);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((message, type = 'info', options = {}) => {
    const { persistent = false, duration = 4000, id = Math.random().toString(36).substring(2, 9) } = options;
    
    if (typeof message === 'string') {
      const existing = toastsRef.current.find((t) => t.message === message);
      if (existing) {
        return existing.id;
      }
    }

    setToasts((prev) => {
      if (typeof message === 'string' && prev.some((t) => t.message === message)) {
        return prev;
      }
      const newToast = { id, message, type, persistent, duration };
      if (prev.length >= 3) {
        return [...prev.slice(1), newToast];
      }
      return [...prev, newToast];
    });
    return id;
  }, []);

  return (
    <ToastContext.Provider value={{ addToast, removeToast }}>
      {children}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    return {
      addToast: () => {},
      removeToast: () => {}
    };
  }
  return context;
}

const iconMap = {
  success: <CheckCircle size={20} className="toast-icon-success" />,
  error: <XCircle size={20} className="toast-icon-error" />,
  info: <Info size={20} className="toast-icon-info" />,
  warning: <Warning size={20} className="toast-icon-warning" />
};

function ToastContainer({ toasts, onRemove }) {
  return (
    <div className="toast-container" data-testid="toast-container">
      {toasts.map((toast) => (
        <ToastItem 
          key={toast.id} 
          id={toast.id} 
          message={toast.message} 
          type={toast.type} 
          persistent={toast.persistent}
          duration={toast.duration}
          onRemove={onRemove} 
        />
      ))}
    </div>
  );
}

function ToastItem({ id, message, type, persistent, duration, onRemove }) {
  const [isRemoving, setIsRemoving] = useState(false);

  useEffect(() => {
    if (persistent) return;

    const dismissTimer = setTimeout(() => {
      handleClose();
    }, duration || 4000); // Auto-dismiss after configured duration

    return () => clearTimeout(dismissTimer);
  }, [id, persistent, duration]);

  const handleClose = () => {
    setIsRemoving(true);
    const fadeTimer = setTimeout(() => {
      onRemove(id);
    }, 200); // Match fade-out animation duration (200ms)
    return () => clearTimeout(fadeTimer);
  };

  return (
    <div 
      className={`toast-item toast-${type} ${isRemoving ? 'removing' : ''}`}
      role="alert"
      aria-live="polite"
      data-testid={`toast-${type}`}
    >
      <div className="toast-icon">
        {iconMap[type] || iconMap.info}
      </div>
      <div className="toast-message">
        {message}
      </div>
    </div>
  );
}
