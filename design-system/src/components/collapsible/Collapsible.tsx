import type { Collapsible as CollapsibleNamespace } from '@base-ui/react/collapsible';

import * as React from 'react';
import { Collapsible as BaseCollapsible } from '@base-ui/react/collapsible';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

const CollapsibleRoot = React.forwardRef<HTMLDivElement, CollapsibleNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseCollapsible.Root ref={ref} className={cn('flex flex-col', className)} {...props} />
  ),
);
CollapsibleRoot.displayName = 'Collapsible.Root';

const CollapsibleTrigger = React.forwardRef<HTMLButtonElement, CollapsibleNamespace.Trigger.Props>(
  ({ className, ...props }, ref) => (
    <BaseCollapsible.Trigger
      ref={ref}
      className={cn(
        'flex items-center gap-2 text-sm font-medium text-ink',
        focusRing,
        disabledStyles,
        className,
      )}
      {...props}
    />
  ),
);
CollapsibleTrigger.displayName = 'Collapsible.Trigger';

const CollapsiblePanel = React.forwardRef<HTMLDivElement, CollapsibleNamespace.Panel.Props>(
  ({ className, ...props }, ref) => (
    <BaseCollapsible.Panel
      ref={ref}
      className={cn(
        'overflow-hidden text-sm text-ink transition-[height]',
        'h-[var(--collapsible-panel-height)]',
        className,
      )}
      {...props}
    />
  ),
);
CollapsiblePanel.displayName = 'Collapsible.Panel';

export const Collapsible = {
  Root: CollapsibleRoot,
  Trigger: CollapsibleTrigger,
  Panel: CollapsiblePanel,
};
