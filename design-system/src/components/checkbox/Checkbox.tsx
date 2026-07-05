import type { Checkbox as CheckboxNamespace } from '@base-ui/react/checkbox';

import * as React from 'react';
import { Checkbox as BaseCheckbox } from '@base-ui/react/checkbox';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

const CheckboxRoot = React.forwardRef<HTMLButtonElement, CheckboxNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseCheckbox.Root
      ref={ref}
      className={cn(
        'flex size-5 items-center justify-center rounded border border-neutral-300 bg-neutral-0',
        'data-[checked]:border-brand-600 data-[checked]:bg-brand-600',
        'data-[indeterminate]:border-brand-600 data-[indeterminate]:bg-brand-600',
        'data-[invalid]:border-danger-500',
        focusRing,
        disabledStyles,
        className,
      )}
      {...props}
    />
  ),
);
CheckboxRoot.displayName = 'Checkbox.Root';

const CheckboxIndicator = React.forwardRef<HTMLSpanElement, CheckboxNamespace.Indicator.Props>(
  ({ className, ...props }, ref) => (
    <BaseCheckbox.Indicator ref={ref} className={cn('flex text-neutral-0', className)} {...props}>
      <svg viewBox="0 0 16 16" fill="none" className="size-3.5" aria-hidden="true">
        <path
          d="M3.5 8.5L6.5 11.5L12.5 4.5"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </BaseCheckbox.Indicator>
  ),
);
CheckboxIndicator.displayName = 'Checkbox.Indicator';

export const Checkbox = {
  Root: CheckboxRoot,
  Indicator: CheckboxIndicator,
};
