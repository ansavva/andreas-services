import type { Switch as SwitchNamespace } from '@base-ui/react/switch';

import * as React from 'react';
import { Switch as BaseSwitch } from '@base-ui/react/switch';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

const SwitchRoot = React.forwardRef<HTMLButtonElement, SwitchNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseSwitch.Root
      ref={ref}
      className={cn(
        'relative flex h-6 w-10 items-center rounded-full bg-neutral-300 transition-colors',
        'data-[checked]:bg-brand-600',
        focusRing,
        disabledStyles,
        className,
      )}
      {...props}
    />
  ),
);
SwitchRoot.displayName = 'Switch.Root';

const SwitchThumb = React.forwardRef<HTMLSpanElement, SwitchNamespace.Thumb.Props>(
  ({ className, ...props }, ref) => (
    <BaseSwitch.Thumb
      ref={ref}
      className={cn(
        'size-4.5 translate-x-1 rounded-full bg-neutral-0 shadow-sm transition-transform',
        'data-[checked]:translate-x-[1.125rem]',
        className,
      )}
      {...props}
    />
  ),
);
SwitchThumb.displayName = 'Switch.Thumb';

export const Switch = {
  Root: SwitchRoot,
  Thumb: SwitchThumb,
};
