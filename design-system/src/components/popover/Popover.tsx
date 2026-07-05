import type { Popover as PopoverNamespace } from '@base-ui/react/popover';

import * as React from 'react';
import { Popover as BasePopover } from '@base-ui/react/popover';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

const transition =
  'transition-opacity data-[starting-style]:opacity-0 data-[ending-style]:opacity-0';

const PopoverPopup = React.forwardRef<HTMLDivElement, PopoverNamespace.Popup.Props>(
  ({ className, ...props }, ref) => (
    <BasePopover.Popup
      ref={ref}
      className={cn(
        'w-72 rounded-lg border border-line bg-card p-4 shadow-lg',
        transition,
        className,
      )}
      {...props}
    />
  ),
);
PopoverPopup.displayName = 'Popover.Popup';

const PopoverArrow = React.forwardRef<HTMLDivElement, PopoverNamespace.Arrow.Props>(
  ({ className, ...props }, ref) => (
    <BasePopover.Arrow ref={ref} className={cn('fill-card', className)} {...props} />
  ),
);
PopoverArrow.displayName = 'Popover.Arrow';

const PopoverTitle = React.forwardRef<HTMLHeadingElement, PopoverNamespace.Title.Props>(
  ({ className, ...props }, ref) => (
    <BasePopover.Title
      ref={ref}
      className={cn('text-sm font-semibold text-ink', className)}
      {...props}
    />
  ),
);
PopoverTitle.displayName = 'Popover.Title';

const PopoverDescription = React.forwardRef<
  HTMLParagraphElement,
  PopoverNamespace.Description.Props
>(({ className, ...props }, ref) => (
  <BasePopover.Description
    ref={ref}
    className={cn('mt-1 text-sm text-muted', className)}
    {...props}
  />
));
PopoverDescription.displayName = 'Popover.Description';

const PopoverClose = React.forwardRef<HTMLButtonElement, PopoverNamespace.Close.Props>(
  ({ className, ...props }, ref) => (
    <BasePopover.Close
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
PopoverClose.displayName = 'Popover.Close';

export const Popover = {
  Root: BasePopover.Root,
  Trigger: BasePopover.Trigger,
  Portal: BasePopover.Portal,
  Backdrop: BasePopover.Backdrop,
  Positioner: BasePopover.Positioner,
  Viewport: BasePopover.Viewport,
  Popup: PopoverPopup,
  Arrow: PopoverArrow,
  Title: PopoverTitle,
  Description: PopoverDescription,
  Close: PopoverClose,
};
