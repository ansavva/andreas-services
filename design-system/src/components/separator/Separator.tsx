import type { Separator as SeparatorNamespace } from '@base-ui/react/separator';

import * as React from 'react';
import { Separator as BaseSeparator } from '@base-ui/react/separator';

import { cn } from '../../lib/cn';

export type SeparatorProps = SeparatorNamespace.Props;

export const Separator = React.forwardRef<HTMLDivElement, SeparatorProps>(
  ({ className, orientation = 'horizontal', ...props }, ref) => (
    <BaseSeparator
      ref={ref}
      orientation={orientation}
      className={cn(
        'bg-line',
        orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px',
        className,
      )}
      {...props}
    />
  ),
);

Separator.displayName = 'Separator';
