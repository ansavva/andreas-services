import type { PreviewCard as PreviewCardNamespace } from '@base-ui/react/preview-card';

import * as React from 'react';
import { PreviewCard as BasePreviewCard } from '@base-ui/react/preview-card';

import { cn } from '../../lib/cn';

const PreviewCardPopup = React.forwardRef<HTMLDivElement, PreviewCardNamespace.Popup.Props>(
  ({ className, ...props }, ref) => (
    <BasePreviewCard.Popup
      ref={ref}
      className={cn(
        'w-80 rounded-lg border border-neutral-200 bg-neutral-0 p-4 shadow-lg',
        'transition-opacity data-[starting-style]:opacity-0 data-[ending-style]:opacity-0',
        className,
      )}
      {...props}
    />
  ),
);
PreviewCardPopup.displayName = 'PreviewCard.Popup';

const PreviewCardArrow = React.forwardRef<HTMLDivElement, PreviewCardNamespace.Arrow.Props>(
  ({ className, ...props }, ref) => (
    <BasePreviewCard.Arrow ref={ref} className={cn('fill-neutral-0', className)} {...props} />
  ),
);
PreviewCardArrow.displayName = 'PreviewCard.Arrow';

export const PreviewCard = {
  Root: BasePreviewCard.Root,
  Trigger: BasePreviewCard.Trigger,
  Portal: BasePreviewCard.Portal,
  Backdrop: BasePreviewCard.Backdrop,
  Positioner: BasePreviewCard.Positioner,
  Viewport: BasePreviewCard.Viewport,
  Popup: PreviewCardPopup,
  Arrow: PreviewCardArrow,
  Handle: BasePreviewCard.Handle,
  createHandle: BasePreviewCard.createHandle,
};
