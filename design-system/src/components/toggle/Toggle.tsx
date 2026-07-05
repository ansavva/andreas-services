import type { Toggle as ToggleNamespace } from '@base-ui/react/toggle';

import * as React from 'react';
import { Toggle as BaseToggle } from '@base-ui/react/toggle';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

export type ToggleProps = ToggleNamespace.Props;

export const Toggle = React.forwardRef<HTMLButtonElement, ToggleProps>(
  ({ className, ...props }, ref) => (
    <BaseToggle
      ref={ref}
      className={cn(
        'inline-flex h-9 items-center justify-center rounded-md px-3 text-sm font-medium text-neutral-700',
        'hover:bg-neutral-100',
        'data-[pressed]:bg-brand-100 data-[pressed]:text-brand-700',
        focusRing,
        disabledStyles,
        className,
      )}
      {...props}
    />
  ),
);

Toggle.displayName = 'Toggle';
