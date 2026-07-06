import type { Field as FieldNamespace } from '@base-ui/react/field';

import * as React from 'react';
import { Field as BaseField } from '@base-ui/react/field';

import { cn } from '../../lib/cn';

const FieldRoot = React.forwardRef<HTMLDivElement, FieldNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseField.Root ref={ref} className={cn('flex flex-col gap-1.5', className)} {...props} />
  ),
);
FieldRoot.displayName = 'Field.Root';

const FieldLabel = React.forwardRef<HTMLLabelElement, FieldNamespace.Label.Props>(
  ({ className, ...props }, ref) => (
    <BaseField.Label
      ref={ref}
      className={cn('text-sm font-medium text-ink data-[disabled]:text-muted', className)}
      {...props}
    />
  ),
);
FieldLabel.displayName = 'Field.Label';

const FieldControl = React.forwardRef<HTMLInputElement, FieldNamespace.Control.Props>(
  ({ className, ...props }, ref) => (
    <BaseField.Control
      ref={ref}
      className={cn(
        'h-10 rounded-md border border-line bg-card px-3 text-sm text-ink',
        'placeholder:text-muted',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2',
        'data-[disabled]:cursor-not-allowed data-[disabled]:bg-surface-alt data-[disabled]:text-muted',
        'data-[invalid]:border-danger',
        className,
      )}
      {...props}
    />
  ),
);
FieldControl.displayName = 'Field.Control';

const FieldDescription = React.forwardRef<HTMLParagraphElement, FieldNamespace.Description.Props>(
  ({ className, ...props }, ref) => (
    <BaseField.Description ref={ref} className={cn('text-sm text-muted', className)} {...props} />
  ),
);
FieldDescription.displayName = 'Field.Description';

const FieldError = React.forwardRef<HTMLParagraphElement, FieldNamespace.Error.Props>(
  ({ className, ...props }, ref) => (
    <BaseField.Error ref={ref} className={cn('text-sm text-danger', className)} {...props} />
  ),
);
FieldError.displayName = 'Field.Error';

const FieldItem = React.forwardRef<HTMLDivElement, FieldNamespace.Item.Props>(
  ({ className, ...props }, ref) => (
    <BaseField.Item ref={ref} className={cn('flex items-center gap-2', className)} {...props} />
  ),
);
FieldItem.displayName = 'Field.Item';

export const Field = {
  Root: FieldRoot,
  Label: FieldLabel,
  Control: FieldControl,
  Description: FieldDescription,
  Error: FieldError,
  Item: FieldItem,
  Validity: BaseField.Validity,
};
