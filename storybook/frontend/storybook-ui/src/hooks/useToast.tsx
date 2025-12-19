import React, { createContext, useContext, useState, useCallback } from 'react';
import { Card, CardBody } from '@nextui-org/react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faCheckCircle,
  faExclamationCircle,
  faInfoCircle,
  faTimesCircle,
  faTimes,
} from '@fortawesome/free-solid-svg-icons';

type ToastType = 'success' | 'error' | 'warning' | 'info';

interface Toast {
  id: string;
  message: string;
  type: ToastType;
}

interface ToastContextType {
  showToast: (message: string, type?: ToastType) => void;
  showSuccess: (message: string) => void;
  showError: (message: string) => void;
  showWarning: (message: string) => void;
  showInfo: (message: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return context;
};

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback((message: string, type: ToastType = 'info') => {
    const id = `toast-${Date.now()}-${Math.random()}`;
    const toast: Toast = { id, message, type };

    setToasts((prev) => [...prev, toast]);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      removeToast(id);
    }, 5000);
  }, [removeToast]);

  const showSuccess = useCallback((message: string) => showToast(message, 'success'), [showToast]);
  const showError = useCallback((message: string) => showToast(message, 'error'), [showToast]);
  const showWarning = useCallback((message: string) => showToast(message, 'warning'), [showToast]);
  const showInfo = useCallback((message: string) => showToast(message, 'info'), [showToast]);

  const getToastStyles = (type: ToastType) => {
    switch (type) {
      case 'success':
        return {
          bg: 'bg-success-50 dark:bg-success-900/20',
          border: 'border-success-500',
          text: 'text-success-700 dark:text-success-300',
          icon: faCheckCircle,
          iconColor: 'text-success-600',
        };
      case 'error':
        return {
          bg: 'bg-danger-50 dark:bg-danger-900/20',
          border: 'border-danger-500',
          text: 'text-danger-700 dark:text-danger-300',
          icon: faTimesCircle,
          iconColor: 'text-danger-600',
        };
      case 'warning':
        return {
          bg: 'bg-warning-50 dark:bg-warning-900/20',
          border: 'border-warning-500',
          text: 'text-warning-700 dark:text-warning-300',
          icon: faExclamationCircle,
          iconColor: 'text-warning-600',
        };
      case 'info':
      default:
        return {
          bg: 'bg-primary-50 dark:bg-primary-900/20',
          border: 'border-primary-500',
          text: 'text-primary-700 dark:text-primary-300',
          icon: faInfoCircle,
          iconColor: 'text-primary-600',
        };
    }
  };

  return (
    <ToastContext.Provider
      value={{
        showToast,
        showSuccess,
        showError,
        showWarning,
        showInfo,
      }}
    >
      {children}

      {/* Toast Container */}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-md">
        {toasts.map((toast) => {
          const styles = getToastStyles(toast.type);
          return (
            <div
              key={toast.id}
              className={`${styles.bg} border-l-4 ${styles.border} rounded-lg shadow-lg animate-slide-in-right`}
            >
              <div className="flex items-start gap-3 p-4">
                <FontAwesomeIcon
                  icon={styles.icon}
                  className={`${styles.iconColor} mt-0.5`}
                  size="lg"
                />
                <p className={`flex-1 ${styles.text} text-sm font-medium`}>
                  {toast.message}
                </p>
                <button
                  onClick={() => removeToast(toast.id)}
                  className={`${styles.text} hover:opacity-70 transition-opacity`}
                  aria-label="Close"
                >
                  <FontAwesomeIcon icon={faTimes} size="sm" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};
