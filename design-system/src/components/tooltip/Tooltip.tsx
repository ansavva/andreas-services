import type { Tooltip as TooltipNamespace } from '@base-ui/react/tooltip';

import * as React from 'react';
import { Tooltip as BaseTooltip } from '@base-ui/react/tooltip';

import { cn } from '../../lib/cn';

const TooltipPopup = React.forwardRef<HTMLDivElement, TooltipNamespace.Popup.Props>(
  ({ className, ...props }, ref) => (
    <BaseTooltip.Popup
      ref={ref}
      className={cn(
        'rounded-md bg-tooltip px-2.5 py-1.5 text-xs text-tooltip-text shadow-md',
        'transition-opacity data-[starting-style]:opacity-0 data-[ending-style]:opacity-0',
        className,
      )}
      {...props}
    />
  ),
);
TooltipPopup.displayName = 'Tooltip.Popup';

const TooltipArrow = React.forwardRef<HTMLDivElement, TooltipNamespace.Arrow.Props>(
  ({ className, ...props }, ref) => (
    <BaseTooltip.Arrow ref={ref} className={cn('fill-forest', className)} {...props} />
  ),
);
TooltipArrow.displayName = 'Tooltip.Arrow';

export const Tooltip = {
  Root: BaseTooltip.Root,
  Trigger: BaseTooltip.Trigger,
  Portal: BaseTooltip.Portal,
  Positioner: BaseTooltip.Positioner,
  Viewport: BaseTooltip.Viewport,
  Popup: TooltipPopup,
  Arrow: TooltipArrow,
  Provider: BaseTooltip.Provider,
  Handle: BaseTooltip.Handle,
  createHandle: BaseTooltip.createHandle,
};
