import React, { createContext, useContext, useCallback } from 'react';
import { addToast, ToastProvider as HeroUIToastProvider, Button } from "@heroui/react";
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faCopy } from '@fortawesome/free-solid-svg-icons';

type ToastType = 'success' | 'danger' | 'warning' | 'default';

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
  const copyToClipboard = useCallback((text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      addToast({
        description: 'Copied to clipboard',
        color: 'success',
        timeout: 2000,
      });
    }).catch(() => {
      addToast({
        description: 'Failed to copy',
        color: 'danger',
        timeout: 2000,
      });
    });
  }, []);

  const showToast = useCallback((message: string, type: ToastType = 'default') => {
    addToast({
      description: (
        <div className="flex items-center justify-between gap-2 w-full">
          <span className="flex-1">{message}</span>
          <Button
            size="sm"
            variant="light"
            isIconOnly
            onPress={() => copyToClipboard(message)}
            className="min-w-fit"
            aria-label="Copy to clipboard"
          >
            <FontAwesomeIcon icon={faCopy} />
          </Button>
        </div>
      ),
      color: type,
      timeout: 5000,
    });
  }, [copyToClipboard]);

  const showSuccess = useCallback((message: string) => showToast(message, 'success'), [showToast]);
  const showError = useCallback((message: string) => showToast(message, 'danger'), [showToast]);
  const showWarning = useCallback((message: string) => showToast(message, 'warning'), [showToast]);
  const showInfo = useCallback((message: string) => showToast(message, 'default'), [showToast]);

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
      <HeroUIToastProvider placement="top-right" />
      {children}
    </ToastContext.Provider>
  );
};
