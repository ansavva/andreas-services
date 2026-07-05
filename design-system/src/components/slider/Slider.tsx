import type { Slider as SliderNamespace } from '@base-ui/react/slider';

import * as React from 'react';
import { Slider as BaseSlider } from '@base-ui/react/slider';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

const SliderRoot = React.forwardRef<HTMLDivElement, SliderNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseSlider.Root
      ref={ref}
      className={cn('flex flex-col gap-2', disabledStyles, className)}
      {...props}
    />
  ),
);
SliderRoot.displayName = 'Slider.Root';

const SliderLabel = React.forwardRef<HTMLDivElement, SliderNamespace.Label.Props>(
  ({ className, ...props }, ref) => (
    <BaseSlider.Label
      ref={ref}
      className={cn('text-sm font-medium text-neutral-900', className)}
      {...props}
    />
  ),
);
SliderLabel.displayName = 'Slider.Label';

const SliderValue = React.forwardRef<HTMLOutputElement, SliderNamespace.Value.Props>(
  ({ className, ...props }, ref) => (
    <BaseSlider.Value ref={ref} className={cn('text-sm text-neutral-500', className)} {...props} />
  ),
);
SliderValue.displayName = 'Slider.Value';

const SliderControl = React.forwardRef<HTMLDivElement, SliderNamespace.Control.Props>(
  ({ className, ...props }, ref) => (
    <BaseSlider.Control
      ref={ref}
      className={cn('relative flex h-5 w-full items-center', className)}
      {...props}
    />
  ),
);
SliderControl.displayName = 'Slider.Control';

const SliderTrack = React.forwardRef<HTMLDivElement, SliderNamespace.Track.Props>(
  ({ className, ...props }, ref) => (
    <BaseSlider.Track
      ref={ref}
      className={cn('h-1.5 w-full rounded-full bg-neutral-200', className)}
      {...props}
    />
  ),
);
SliderTrack.displayName = 'Slider.Track';

const SliderIndicator = React.forwardRef<HTMLDivElement, SliderNamespace.Indicator.Props>(
  ({ className, ...props }, ref) => (
    <BaseSlider.Indicator
      ref={ref}
      className={cn('rounded-full bg-brand-600', className)}
      {...props}
    />
  ),
);
SliderIndicator.displayName = 'Slider.Indicator';

const SliderThumb = React.forwardRef<HTMLDivElement, SliderNamespace.Thumb.Props>(
  ({ className, ...props }, ref) => (
    <BaseSlider.Thumb
      ref={ref}
      className={cn(
        'size-4 rounded-full border-2 border-brand-600 bg-neutral-0 shadow-sm',
        focusRing,
        className,
      )}
      {...props}
    />
  ),
);
SliderThumb.displayName = 'Slider.Thumb';

export const Slider = {
  Root: SliderRoot,
  Label: SliderLabel,
  Value: SliderValue,
  Control: SliderControl,
  Track: SliderTrack,
  Indicator: SliderIndicator,
  Thumb: SliderThumb,
};
