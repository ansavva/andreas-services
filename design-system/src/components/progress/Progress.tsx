import type { Progress as ProgressNamespace } from '@base-ui/react/progress';

import * as React from 'react';
import { Progress as BaseProgress } from '@base-ui/react/progress';

import { cn } from '../../lib/cn';

const ProgressRoot = React.forwardRef<HTMLDivElement, ProgressNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseProgress.Root ref={ref} className={cn('flex flex-col gap-1.5', className)} {...props} />
  ),
);
ProgressRoot.displayName = 'Progress.Root';

const ProgressLabel = React.forwardRef<HTMLSpanElement, ProgressNamespace.Label.Props>(
  ({ className, ...props }, ref) => (
    <BaseProgress.Label
      ref={ref}
      className={cn('text-sm font-medium text-neutral-900', className)}
      {...props}
    />
  ),
);
ProgressLabel.displayName = 'Progress.Label';

const ProgressValue = React.forwardRef<HTMLSpanElement, ProgressNamespace.Value.Props>(
  ({ className, ...props }, ref) => (
    <BaseProgress.Value
      ref={ref}
      className={cn('text-sm text-neutral-500', className)}
      {...props}
    />
  ),
);
ProgressValue.displayName = 'Progress.Value';

const ProgressTrack = React.forwardRef<HTMLDivElement, ProgressNamespace.Track.Props>(
  ({ className, ...props }, ref) => (
    <BaseProgress.Track
      ref={ref}
      className={cn('h-2 overflow-hidden rounded-full bg-neutral-200', className)}
      {...props}
    />
  ),
);
ProgressTrack.displayName = 'Progress.Track';

const ProgressIndicator = React.forwardRef<HTMLDivElement, ProgressNamespace.Indicator.Props>(
  ({ className, ...props }, ref) => (
    <BaseProgress.Indicator
      ref={ref}
      className={cn('h-full rounded-full bg-brand-600 transition-all', className)}
      {...props}
    />
  ),
);
ProgressIndicator.displayName = 'Progress.Indicator';

export const Progress = {
  Root: ProgressRoot,
  Label: ProgressLabel,
  Value: ProgressValue,
  Track: ProgressTrack,
  Indicator: ProgressIndicator,
};
