import type { Toolbar as ToolbarNamespace } from '@base-ui/react/toolbar';

import * as React from 'react';
import { Toolbar as BaseToolbar } from '@base-ui/react/toolbar';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

const ToolbarRoot = React.forwardRef<HTMLDivElement, ToolbarNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseToolbar.Root
      ref={ref}
      className={cn(
        'flex items-center gap-1 rounded-md border border-neutral-200 bg-neutral-0 p-1',
        className,
      )}
      {...props}
    />
  ),
);
ToolbarRoot.displayName = 'Toolbar.Root';

const ToolbarGroup = React.forwardRef<HTMLDivElement, ToolbarNamespace.Group.Props>(
  ({ className, ...props }, ref) => (
    <BaseToolbar.Group ref={ref} className={cn('flex items-center gap-1', className)} {...props} />
  ),
);
ToolbarGroup.displayName = 'Toolbar.Group';

const toolbarItemStyles = cn(
  'inline-flex h-8 items-center justify-center rounded px-2 text-sm font-medium text-neutral-700',
  'hover:bg-neutral-100 data-[pressed]:bg-brand-100 data-[pressed]:text-brand-700',
  focusRing,
  disabledStyles,
);

const ToolbarButton = React.forwardRef<HTMLButtonElement, ToolbarNamespace.Button.Props>(
  ({ className, ...props }, ref) => (
    <BaseToolbar.Button ref={ref} className={cn(toolbarItemStyles, className)} {...props} />
  ),
);
ToolbarButton.displayName = 'Toolbar.Button';

const ToolbarLink = React.forwardRef<HTMLAnchorElement, ToolbarNamespace.Link.Props>(
  ({ className, ...props }, ref) => (
    <BaseToolbar.Link ref={ref} className={cn(toolbarItemStyles, className)} {...props} />
  ),
);
ToolbarLink.displayName = 'Toolbar.Link';

const ToolbarInput = React.forwardRef<HTMLInputElement, ToolbarNamespace.Input.Props>(
  ({ className, ...props }, ref) => (
    <BaseToolbar.Input
      ref={ref}
      className={cn(
        'h-8 rounded border border-neutral-300 px-2 text-sm text-neutral-900',
        focusRing,
        className,
      )}
      {...props}
    />
  ),
);
ToolbarInput.displayName = 'Toolbar.Input';

const ToolbarSeparator = React.forwardRef<HTMLDivElement, ToolbarNamespace.Separator.Props>(
  ({ className, orientation = 'vertical', ...props }, ref) => (
    <BaseToolbar.Separator
      ref={ref}
      orientation={orientation}
      className={cn(
        'bg-neutral-200',
        orientation === 'vertical' ? 'mx-1 h-6 w-px' : 'my-1 h-px w-full',
        className,
      )}
      {...props}
    />
  ),
);
ToolbarSeparator.displayName = 'Toolbar.Separator';

export const Toolbar = {
  Root: ToolbarRoot,
  Group: ToolbarGroup,
  Button: ToolbarButton,
  Link: ToolbarLink,
  Input: ToolbarInput,
  Separator: ToolbarSeparator,
};
