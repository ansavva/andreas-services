import type { ScrollArea as ScrollAreaNamespace } from '@base-ui/react/scroll-area';

import * as React from 'react';
import { ScrollArea as BaseScrollArea } from '@base-ui/react/scroll-area';

import { cn } from '../../lib/cn';

const ScrollAreaRoot = React.forwardRef<HTMLDivElement, ScrollAreaNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseScrollArea.Root
      ref={ref}
      className={cn('relative overflow-hidden', className)}
      {...props}
    />
  ),
);
ScrollAreaRoot.displayName = 'ScrollArea.Root';

const ScrollAreaViewport = React.forwardRef<HTMLDivElement, ScrollAreaNamespace.Viewport.Props>(
  ({ className, ...props }, ref) => (
    <BaseScrollArea.Viewport ref={ref} className={cn('size-full', className)} {...props} />
  ),
);
ScrollAreaViewport.displayName = 'ScrollArea.Viewport';

const ScrollAreaContent = React.forwardRef<HTMLDivElement, ScrollAreaNamespace.Content.Props>(
  (props, ref) => <BaseScrollArea.Content ref={ref} {...props} />,
);
ScrollAreaContent.displayName = 'ScrollArea.Content';

const ScrollAreaScrollbar = React.forwardRef<HTMLDivElement, ScrollAreaNamespace.Scrollbar.Props>(
  ({ className, orientation = 'vertical', ...props }, ref) => (
    <BaseScrollArea.Scrollbar
      ref={ref}
      orientation={orientation}
      className={cn(
        'flex touch-none select-none bg-surface-alt p-0.5 transition-opacity',
        'data-[orientation=vertical]:w-2.5',
        'data-[orientation=horizontal]:h-2.5 data-[orientation=horizontal]:flex-col',
        className,
      )}
      {...props}
    />
  ),
);
ScrollAreaScrollbar.displayName = 'ScrollArea.Scrollbar';

const ScrollAreaThumb = React.forwardRef<HTMLDivElement, ScrollAreaNamespace.Thumb.Props>(
  ({ className, ...props }, ref) => (
    <BaseScrollArea.Thumb
      ref={ref}
      className={cn('flex-1 rounded-full bg-muted', className)}
      {...props}
    />
  ),
);
ScrollAreaThumb.displayName = 'ScrollArea.Thumb';

const ScrollAreaCorner = React.forwardRef<HTMLDivElement, ScrollAreaNamespace.Corner.Props>(
  (props, ref) => <BaseScrollArea.Corner ref={ref} {...props} />,
);
ScrollAreaCorner.displayName = 'ScrollArea.Corner';

export const ScrollArea = {
  Root: ScrollAreaRoot,
  Viewport: ScrollAreaViewport,
  Content: ScrollAreaContent,
  Scrollbar: ScrollAreaScrollbar,
  Thumb: ScrollAreaThumb,
  Corner: ScrollAreaCorner,
};
