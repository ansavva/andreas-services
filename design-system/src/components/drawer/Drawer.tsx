import type { Drawer as DrawerNamespace } from '@base-ui/react/drawer';

import * as React from 'react';
import { Drawer as BaseDrawer } from '@base-ui/react/drawer';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

const transition = 'transition-all data-[starting-style]:opacity-0 data-[ending-style]:opacity-0';

const DrawerBackdrop = React.forwardRef<HTMLDivElement, DrawerNamespace.Backdrop.Props>(
  ({ className, ...props }, ref) => (
    <BaseDrawer.Backdrop
      ref={ref}
      className={cn('fixed inset-0 bg-overlay', transition, className)}
      {...props}
    />
  ),
);
DrawerBackdrop.displayName = 'Drawer.Backdrop';

const DrawerViewport = React.forwardRef<HTMLDivElement, DrawerNamespace.Viewport.Props>(
  ({ className, ...props }, ref) => (
    <BaseDrawer.Viewport ref={ref} className={cn('fixed inset-0 flex', className)} {...props} />
  ),
);
DrawerViewport.displayName = 'Drawer.Viewport';

const DrawerPopup = React.forwardRef<HTMLDivElement, DrawerNamespace.Popup.Props>(
  ({ className, ...props }, ref) => (
    <BaseDrawer.Popup
      ref={ref}
      className={cn(
        'ml-auto flex h-full w-full max-w-sm flex-col bg-card p-6 shadow-lg',
        transition,
        className,
      )}
      {...props}
    />
  ),
);
DrawerPopup.displayName = 'Drawer.Popup';

const DrawerContent = React.forwardRef<HTMLDivElement, DrawerNamespace.Content.Props>(
  ({ className, ...props }, ref) => (
    <BaseDrawer.Content ref={ref} className={cn('flex-1 overflow-y-auto', className)} {...props} />
  ),
);
DrawerContent.displayName = 'Drawer.Content';

function DrawerTitle({ className, ...props }: DrawerNamespace.Title.Props) {
  return (
    <BaseDrawer.Title className={cn('text-lg font-semibold text-ink', className)} {...props} />
  );
}
DrawerTitle.displayName = 'Drawer.Title';

function DrawerDescription({ className, ...props }: DrawerNamespace.Description.Props) {
  return <BaseDrawer.Description className={cn('mt-2 text-sm text-muted', className)} {...props} />;
}
DrawerDescription.displayName = 'Drawer.Description';

function DrawerClose({ className, ...props }: DrawerNamespace.Close.Props) {
  return (
    <BaseDrawer.Close
      className={cn(
        'inline-flex h-8 items-center justify-center rounded-md px-3 text-sm font-medium text-ink hover:bg-surface-alt',
        focusRing,
        disabledStyles,
        className,
      )}
      {...props}
    />
  );
}
DrawerClose.displayName = 'Drawer.Close';

const DrawerSwipeArea = React.forwardRef<HTMLDivElement, DrawerNamespace.SwipeArea.Props>(
  ({ className, ...props }, ref) => (
    <BaseDrawer.SwipeArea ref={ref} className={cn('touch-none', className)} {...props} />
  ),
);
DrawerSwipeArea.displayName = 'Drawer.SwipeArea';

export const Drawer = {
  Root: BaseDrawer.Root,
  Trigger: BaseDrawer.Trigger,
  Portal: BaseDrawer.Portal,
  Provider: BaseDrawer.Provider,
  VirtualKeyboardProvider: BaseDrawer.VirtualKeyboardProvider,
  Backdrop: DrawerBackdrop,
  Viewport: DrawerViewport,
  Popup: DrawerPopup,
  Content: DrawerContent,
  Title: DrawerTitle,
  Description: DrawerDescription,
  Close: DrawerClose,
  SwipeArea: DrawerSwipeArea,
  Indent: BaseDrawer.Indent,
  IndentBackground: BaseDrawer.IndentBackground,
  Handle: BaseDrawer.Handle,
  createHandle: BaseDrawer.createHandle,
};
