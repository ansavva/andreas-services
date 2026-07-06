import type { Tabs as TabsNamespace } from '@base-ui/react/tabs';

import * as React from 'react';
import { Tabs as BaseTabs } from '@base-ui/react/tabs';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

const TabsRoot = React.forwardRef<HTMLDivElement, TabsNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseTabs.Root ref={ref} className={cn('flex flex-col gap-2', className)} {...props} />
  ),
);
TabsRoot.displayName = 'Tabs.Root';

const TabsList = React.forwardRef<HTMLDivElement, TabsNamespace.List.Props>(
  ({ className, ...props }, ref) => (
    <BaseTabs.List
      ref={ref}
      className={cn('relative flex gap-1 border-b border-line', className)}
      {...props}
    />
  ),
);
TabsList.displayName = 'Tabs.List';

const TabsTab = React.forwardRef<HTMLElement, TabsNamespace.Tab.Props>(
  ({ className, ...props }, ref) => (
    <BaseTabs.Tab
      ref={ref}
      className={cn(
        'px-3 py-2 text-sm font-medium text-muted outline-none hover:text-ink',
        'data-[selected]:text-accent',
        focusRing,
        disabledStyles,
        className,
      )}
      {...props}
    />
  ),
);
TabsTab.displayName = 'Tabs.Tab';

const TabsIndicator = React.forwardRef<HTMLSpanElement, TabsNamespace.Indicator.Props>(
  ({ className, ...props }, ref) => (
    <BaseTabs.Indicator
      ref={ref}
      className={cn(
        'absolute bottom-0 h-0.5 rounded-full bg-accent transition-all',
        'left-[var(--active-tab-left)] w-[var(--active-tab-width)]',
        className,
      )}
      {...props}
    />
  ),
);
TabsIndicator.displayName = 'Tabs.Indicator';

const TabsPanel = React.forwardRef<HTMLDivElement, TabsNamespace.Panel.Props>(
  ({ className, ...props }, ref) => (
    <BaseTabs.Panel ref={ref} className={cn('pt-4 text-sm text-ink', className)} {...props} />
  ),
);
TabsPanel.displayName = 'Tabs.Panel';

export const Tabs = {
  Root: TabsRoot,
  List: TabsList,
  Tab: TabsTab,
  Indicator: TabsIndicator,
  Panel: TabsPanel,
};
