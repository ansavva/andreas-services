import type { Toast as ToastNamespace } from '@base-ui/react/toast';

import * as React from 'react';
import { Toast as BaseToast } from '@base-ui/react/toast';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

const ToastViewport = React.forwardRef<HTMLDivElement, ToastNamespace.Viewport.Props>(
  ({ className, ...props }, ref) => (
    <BaseToast.Viewport
      ref={ref}
      className={cn('fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2', className)}
      {...props}
    />
  ),
);
ToastViewport.displayName = 'Toast.Viewport';

const ToastRoot = React.forwardRef<HTMLDivElement, ToastNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseToast.Root
      ref={ref}
      className={cn(
        'rounded-lg border border-line bg-card p-4 shadow-lg',
        'transition-all data-[starting-style]:translate-x-full data-[ending-style]:opacity-0',
        className,
      )}
      {...props}
    />
  ),
);
ToastRoot.displayName = 'Toast.Root';

const ToastTitle = React.forwardRef<HTMLHeadingElement, ToastNamespace.Title.Props>(
  ({ className, ...props }, ref) => (
    <BaseToast.Title
      ref={ref}
      className={cn('text-sm font-semibold text-ink', className)}
      {...props}
    />
  ),
);
ToastTitle.displayName = 'Toast.Title';

const ToastDescription = React.forwardRef<HTMLParagraphElement, ToastNamespace.Description.Props>(
  ({ className, ...props }, ref) => (
    <BaseToast.Description
      ref={ref}
      className={cn('mt-1 text-sm text-muted', className)}
      {...props}
    />
  ),
);
ToastDescription.displayName = 'Toast.Description';

const ToastClose = React.forwardRef<HTMLButtonElement, ToastNamespace.Close.Props>(
  ({ className, ...props }, ref) => (
    <BaseToast.Close
      ref={ref}
      className={cn(
        'absolute right-2 top-2 rounded p-1 text-muted hover:bg-surface-alt hover:text-ink',
        focusRing,
        className,
      )}
      {...props}
    />
  ),
);
ToastClose.displayName = 'Toast.Close';

const ToastAction = React.forwardRef<HTMLButtonElement, ToastNamespace.Action.Props>(
  ({ className, ...props }, ref) => (
    <BaseToast.Action
      ref={ref}
      className={cn(
        'mt-2 inline-flex h-8 items-center justify-center rounded-md px-3 text-sm font-medium text-accent hover:bg-surface-alt',
        focusRing,
        disabledStyles,
        className,
      )}
      {...props}
    />
  ),
);
ToastAction.displayName = 'Toast.Action';

export const Toast = {
  Provider: BaseToast.Provider,
  Portal: BaseToast.Portal,
  Positioner: BaseToast.Positioner,
  Arrow: BaseToast.Arrow,
  Viewport: ToastViewport,
  Root: ToastRoot,
  Title: ToastTitle,
  Description: ToastDescription,
  Close: ToastClose,
  Action: ToastAction,
};

export const useToastManager = BaseToast.useToastManager;
export const createToastManager = BaseToast.createToastManager;
