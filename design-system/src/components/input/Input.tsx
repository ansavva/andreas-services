import type { Input as InputNamespace } from '@base-ui/react/input';

import * as React from 'react';
import { Input as BaseInput } from '@base-ui/react/input';

import { cn } from '../../lib/cn';
import { focusRing } from '../../lib/styles';

export type InputProps = InputNamespace.Props;

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) => (
    <BaseInput
      ref={ref}
      className={cn(
        'h-10 w-full rounded-md border border-neutral-300 bg-neutral-0 px-3 text-sm text-neutral-900',
        'placeholder:text-neutral-400',
        focusRing,
        'data-[disabled]:cursor-not-allowed data-[disabled]:bg-neutral-100 data-[disabled]:text-neutral-400',
        'data-[invalid]:border-danger-500',
        className,
      )}
      {...props}
    />
  ),
);

Input.displayName = 'Input';
