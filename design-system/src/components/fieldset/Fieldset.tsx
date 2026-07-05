import type { Fieldset as FieldsetNamespace } from '@base-ui/react/fieldset';

import * as React from 'react';
import { Fieldset as BaseFieldset } from '@base-ui/react/fieldset';

import { cn } from '../../lib/cn';

const FieldsetRoot = React.forwardRef<HTMLFieldSetElement, FieldsetNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseFieldset.Root
      ref={ref}
      className={cn('flex flex-col gap-4 rounded-md border border-line p-4', className)}
      {...props}
    />
  ),
);
FieldsetRoot.displayName = 'Fieldset.Root';

const FieldsetLegend = React.forwardRef<HTMLDivElement, FieldsetNamespace.Legend.Props>(
  ({ className, ...props }, ref) => (
    <BaseFieldset.Legend
      ref={ref}
      className={cn('text-base font-semibold text-ink', className)}
      {...props}
    />
  ),
);
FieldsetLegend.displayName = 'Fieldset.Legend';

export const Fieldset = {
  Root: FieldsetRoot,
  Legend: FieldsetLegend,
};
