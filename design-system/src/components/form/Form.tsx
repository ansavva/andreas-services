import type { Form as FormNamespace } from '@base-ui/react/form';

import * as React from 'react';
import { Form as BaseForm } from '@base-ui/react/form';

import { cn } from '../../lib/cn';

export function Form<FormValues extends Record<string, unknown> = Record<string, unknown>>({
  className,
  ref,
  ...props
}: FormNamespace.Props<FormValues> & { ref?: React.Ref<HTMLFormElement> }) {
  return <BaseForm ref={ref} className={cn('flex flex-col gap-4', className)} {...props} />;
}
