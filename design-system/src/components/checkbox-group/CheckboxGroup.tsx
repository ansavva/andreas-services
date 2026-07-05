import type { CheckboxGroup as CheckboxGroupNamespace } from '@base-ui/react/checkbox-group';

import * as React from 'react';
import { CheckboxGroup as BaseCheckboxGroup } from '@base-ui/react/checkbox-group';

import { cn } from '../../lib/cn';

export type CheckboxGroupProps = CheckboxGroupNamespace.Props;

export const CheckboxGroup = React.forwardRef<HTMLDivElement, CheckboxGroupProps>(
  ({ className, ...props }, ref) => (
    <BaseCheckboxGroup ref={ref} className={cn('flex flex-col gap-2', className)} {...props} />
  ),
);

CheckboxGroup.displayName = 'CheckboxGroup';
