import type { Menubar as MenubarNamespace } from '@base-ui/react/menubar';

import * as React from 'react';
import { Menubar as BaseMenubar } from '@base-ui/react/menubar';

import { cn } from '../../lib/cn';

export type MenubarProps = MenubarNamespace.Props;

export const Menubar = React.forwardRef<HTMLDivElement, MenubarProps>(
  ({ className, ...props }, ref) => (
    <BaseMenubar
      ref={ref}
      className={cn('flex items-center gap-1 rounded-md border border-line bg-card p-1', className)}
      {...props}
    />
  ),
);

Menubar.displayName = 'Menubar';
