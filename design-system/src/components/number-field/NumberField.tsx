import type { NumberField as NumberFieldNamespace } from '@base-ui/react/number-field';

import * as React from 'react';
import { NumberField as BaseNumberField } from '@base-ui/react/number-field';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

const NumberFieldRoot = React.forwardRef<HTMLDivElement, NumberFieldNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseNumberField.Root ref={ref} className={cn('flex flex-col gap-1.5', className)} {...props} />
  ),
);
NumberFieldRoot.displayName = 'NumberField.Root';

const NumberFieldGroup = React.forwardRef<HTMLDivElement, NumberFieldNamespace.Group.Props>(
  ({ className, ...props }, ref) => (
    <BaseNumberField.Group
      ref={ref}
      className={cn(
        'flex h-10 items-stretch overflow-hidden rounded-md border border-neutral-300 bg-neutral-0',
        'data-[invalid]:border-danger-500',
        className,
      )}
      {...props}
    />
  ),
);
NumberFieldGroup.displayName = 'NumberField.Group';

const NumberFieldInput = React.forwardRef<HTMLInputElement, NumberFieldNamespace.Input.Props>(
  ({ className, ...props }, ref) => (
    <BaseNumberField.Input
      ref={ref}
      className={cn(
        'w-full min-w-0 flex-1 px-3 text-sm text-neutral-900 focus:outline-none',
        'data-[disabled]:cursor-not-allowed data-[disabled]:bg-neutral-100 data-[disabled]:text-neutral-400',
        className,
      )}
      {...props}
    />
  ),
);
NumberFieldInput.displayName = 'NumberField.Input';

const stepperButtonStyles = cn(
  'flex w-8 items-center justify-center text-neutral-500 hover:bg-neutral-100 active:bg-neutral-200',
  disabledStyles,
  focusRing,
);

const NumberFieldIncrement = React.forwardRef<
  HTMLButtonElement,
  NumberFieldNamespace.Increment.Props
>(({ className, ...props }, ref) => (
  <BaseNumberField.Increment ref={ref} className={cn(stepperButtonStyles, className)} {...props} />
));
NumberFieldIncrement.displayName = 'NumberField.Increment';

const NumberFieldDecrement = React.forwardRef<
  HTMLButtonElement,
  NumberFieldNamespace.Decrement.Props
>(({ className, ...props }, ref) => (
  <BaseNumberField.Decrement ref={ref} className={cn(stepperButtonStyles, className)} {...props} />
));
NumberFieldDecrement.displayName = 'NumberField.Decrement';

const NumberFieldScrubArea = React.forwardRef<
  HTMLSpanElement,
  NumberFieldNamespace.ScrubArea.Props
>(({ className, ...props }, ref) => (
  <BaseNumberField.ScrubArea ref={ref} className={cn('cursor-ew-resize', className)} {...props} />
));
NumberFieldScrubArea.displayName = 'NumberField.ScrubArea';

export const NumberField = {
  Root: NumberFieldRoot,
  Group: NumberFieldGroup,
  Input: NumberFieldInput,
  Increment: NumberFieldIncrement,
  Decrement: NumberFieldDecrement,
  ScrubArea: NumberFieldScrubArea,
  ScrubAreaCursor: BaseNumberField.ScrubAreaCursor,
};
