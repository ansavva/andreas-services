import type { Dialog as DialogNamespace } from '@base-ui/react/dialog';

import * as React from 'react';
import { Dialog as BaseDialog } from '@base-ui/react/dialog';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

const transition =
  'transition-opacity data-[starting-style]:opacity-0 data-[ending-style]:opacity-0';

const DialogBackdrop = React.forwardRef<HTMLDivElement, DialogNamespace.Backdrop.Props>(
  ({ className, ...props }, ref) => (
    <BaseDialog.Backdrop
      ref={ref}
      className={cn('fixed inset-0 bg-forest/40', transition, className)}
      {...props}
    />
  ),
);
DialogBackdrop.displayName = 'Dialog.Backdrop';

const DialogViewport = React.forwardRef<HTMLDivElement, DialogNamespace.Viewport.Props>(
  ({ className, ...props }, ref) => (
    <BaseDialog.Viewport
      ref={ref}
      className={cn('fixed inset-0 flex items-center justify-center p-4', className)}
      {...props}
    />
  ),
);
DialogViewport.displayName = 'Dialog.Viewport';

const DialogPopup = React.forwardRef<HTMLDivElement, DialogNamespace.Popup.Props>(
  ({ className, ...props }, ref) => (
    <BaseDialog.Popup
      ref={ref}
      className={cn(
        'w-full max-w-md rounded-lg border border-line bg-card p-6 shadow-lg',
        transition,
        'data-[starting-style]:scale-95 data-[ending-style]:scale-95',
        className,
      )}
      {...props}
    />
  ),
);
DialogPopup.displayName = 'Dialog.Popup';

const DialogTitle = React.forwardRef<HTMLHeadingElement, DialogNamespace.Title.Props>(
  ({ className, ...props }, ref) => (
    <BaseDialog.Title
      ref={ref}
      className={cn('text-lg font-semibold text-ink', className)}
      {...props}
    />
  ),
);
DialogTitle.displayName = 'Dialog.Title';

const DialogDescription = React.forwardRef<HTMLParagraphElement, DialogNamespace.Description.Props>(
  ({ className, ...props }, ref) => (
    <BaseDialog.Description
      ref={ref}
      className={cn('mt-2 text-sm text-muted', className)}
      {...props}
    />
  ),
);
DialogDescription.displayName = 'Dialog.Description';

const DialogClose = React.forwardRef<HTMLButtonElement, DialogNamespace.Close.Props>(
  ({ className, ...props }, ref) => (
    <BaseDialog.Close
      ref={ref}
      className={cn(
        'inline-flex h-8 items-center justify-center rounded-md px-3 text-sm font-medium text-ink hover:bg-surface-alt',
        focusRing,
        disabledStyles,
        className,
      )}
      {...props}
    />
  ),
);
DialogClose.displayName = 'Dialog.Close';

export const Dialog = {
  Root: BaseDialog.Root,
  Trigger: BaseDialog.Trigger,
  Portal: BaseDialog.Portal,
  Backdrop: DialogBackdrop,
  Viewport: DialogViewport,
  Popup: DialogPopup,
  Title: DialogTitle,
  Description: DialogDescription,
  Close: DialogClose,
  Handle: BaseDialog.Handle,
  createHandle: BaseDialog.createHandle,
};
