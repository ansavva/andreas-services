import type { ToggleGroup as ToggleGroupNamespace } from '@base-ui/react/toggle-group';

import * as React from 'react';
import { ToggleGroup as BaseToggleGroup } from '@base-ui/react/toggle-group';

import { cn } from '../../lib/cn';

export type ToggleGroupProps = ToggleGroupNamespace.Props;

export const ToggleGroup = React.forwardRef<HTMLDivElement, ToggleGroupProps>(
  ({ className, ...props }, ref) => (
    <BaseToggleGroup
      ref={ref}
      className={cn('inline-flex gap-1 rounded-md bg-surface-alt p-1', className)}
      {...props}
    />
  ),
);

ToggleGroup.displayName = 'ToggleGroup';
