import * as React from 'react';

import { cn } from '../../lib/cn';
import { focusRing } from '../../lib/styles';

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        'min-h-24 w-full resize-y rounded-md border border-line bg-card px-3 py-2 text-sm text-ink',
        'placeholder:text-muted disabled:cursor-not-allowed disabled:bg-surface-alt disabled:text-muted',
        'aria-invalid:border-danger',
        focusRing,
        className,
      )}
      {...props}
    />
  ),
);

Textarea.displayName = 'Textarea';
