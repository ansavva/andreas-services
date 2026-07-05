import type { OTPField as OTPFieldNamespace } from '@base-ui/react/otp-field';

import * as React from 'react';
import { OTPField as BaseOTPField } from '@base-ui/react/otp-field';

import { cn } from '../../lib/cn';
import { focusRing } from '../../lib/styles';
import { Separator } from '../separator';

const OTPFieldRoot = React.forwardRef<HTMLDivElement, OTPFieldNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseOTPField.Root ref={ref} className={cn('flex items-center gap-2', className)} {...props} />
  ),
);
OTPFieldRoot.displayName = 'OTPField.Root';

const OTPFieldInput = React.forwardRef<HTMLInputElement, OTPFieldNamespace.Input.Props>(
  ({ className, ...props }, ref) => (
    <BaseOTPField.Input
      ref={ref}
      className={cn(
        'size-10 rounded-md border border-neutral-300 text-center text-lg text-neutral-900',
        focusRing,
        'data-[invalid]:border-danger-500',
        className,
      )}
      {...props}
    />
  ),
);
OTPFieldInput.displayName = 'OTPField.Input';

export const OTPField = {
  Root: OTPFieldRoot,
  Input: OTPFieldInput,
  Separator,
};
