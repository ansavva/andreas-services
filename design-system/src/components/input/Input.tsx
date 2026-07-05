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
        'h-10 w-full rounded-md border border-line bg-card px-3 text-sm text-ink',
        'placeholder:text-muted',
        focusRing,
        'data-[disabled]:cursor-not-allowed data-[disabled]:bg-surface-alt data-[disabled]:text-muted',
        'data-[invalid]:border-danger',
        className,
      )}
      {...props}
    />
  ),
);

Input.displayName = 'Input';
