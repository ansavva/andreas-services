import type { Radio as RadioNamespace } from '@base-ui/react/radio';
import type { RadioGroup as RadioGroupNamespace } from '@base-ui/react/radio-group';

import * as React from 'react';
import { Radio as BaseRadio } from '@base-ui/react/radio';
import { RadioGroup as BaseRadioGroup } from '@base-ui/react/radio-group';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

const RadioRoot = React.forwardRef<HTMLButtonElement, RadioNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseRadio.Root
      ref={ref}
      className={cn(
        'flex size-5 items-center justify-center rounded-full border border-neutral-300 bg-neutral-0',
        'data-[checked]:border-brand-600',
        'data-[invalid]:border-danger-500',
        focusRing,
        disabledStyles,
        className,
      )}
      {...props}
    />
  ),
);
RadioRoot.displayName = 'Radio.Root';

const RadioIndicator = React.forwardRef<HTMLSpanElement, RadioNamespace.Indicator.Props>(
  ({ className, ...props }, ref) => (
    <BaseRadio.Indicator
      ref={ref}
      className={cn('size-2.5 rounded-full bg-brand-600', className)}
      {...props}
    />
  ),
);
RadioIndicator.displayName = 'Radio.Indicator';

export const Radio = {
  Root: RadioRoot,
  Indicator: RadioIndicator,
};

export const RadioGroup = React.forwardRef<HTMLDivElement, RadioGroupNamespace.Props>(
  ({ className, ...props }, ref) => (
    <BaseRadioGroup ref={ref} className={cn('flex flex-col gap-2', className)} {...props} />
  ),
);

RadioGroup.displayName = 'RadioGroup';
