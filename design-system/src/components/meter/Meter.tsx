import type { Meter as MeterNamespace } from '@base-ui/react/meter';

import * as React from 'react';
import { Meter as BaseMeter } from '@base-ui/react/meter';

import { cn } from '../../lib/cn';

const MeterRoot = React.forwardRef<HTMLDivElement, MeterNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseMeter.Root ref={ref} className={cn('flex flex-col gap-1.5', className)} {...props} />
  ),
);
MeterRoot.displayName = 'Meter.Root';

const MeterLabel = React.forwardRef<HTMLSpanElement, MeterNamespace.Label.Props>(
  ({ className, ...props }, ref) => (
    <BaseMeter.Label
      ref={ref}
      className={cn('text-sm font-medium text-neutral-900', className)}
      {...props}
    />
  ),
);
MeterLabel.displayName = 'Meter.Label';

const MeterValue = React.forwardRef<HTMLSpanElement, MeterNamespace.Value.Props>(
  ({ className, ...props }, ref) => (
    <BaseMeter.Value ref={ref} className={cn('text-sm text-neutral-500', className)} {...props} />
  ),
);
MeterValue.displayName = 'Meter.Value';

const MeterTrack = React.forwardRef<HTMLDivElement, MeterNamespace.Track.Props>(
  ({ className, ...props }, ref) => (
    <BaseMeter.Track
      ref={ref}
      className={cn('h-2 overflow-hidden rounded-full bg-neutral-200', className)}
      {...props}
    />
  ),
);
MeterTrack.displayName = 'Meter.Track';

const MeterIndicator = React.forwardRef<HTMLDivElement, MeterNamespace.Indicator.Props>(
  ({ className, ...props }, ref) => (
    <BaseMeter.Indicator
      ref={ref}
      className={cn('h-full rounded-full bg-brand-600 transition-all', className)}
      {...props}
    />
  ),
);
MeterIndicator.displayName = 'Meter.Indicator';

export const Meter = {
  Root: MeterRoot,
  Label: MeterLabel,
  Value: MeterValue,
  Track: MeterTrack,
  Indicator: MeterIndicator,
};
