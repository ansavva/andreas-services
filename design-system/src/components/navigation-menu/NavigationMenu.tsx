import type { NavigationMenu as NavigationMenuNamespace } from '@base-ui/react/navigation-menu';

import * as React from 'react';
import { NavigationMenu as BaseNavigationMenu } from '@base-ui/react/navigation-menu';

import { cn } from '../../lib/cn';
import { focusRing } from '../../lib/styles';

function NavigationMenuRoot({ className, ...props }: NavigationMenuNamespace.Root.Props) {
  return <BaseNavigationMenu.Root className={cn('relative', className)} {...props} />;
}
NavigationMenuRoot.displayName = 'NavigationMenu.Root';

const NavigationMenuList = React.forwardRef<HTMLUListElement, NavigationMenuNamespace.List.Props>(
  ({ className, ...props }, ref) => (
    <BaseNavigationMenu.List
      ref={ref}
      className={cn('flex items-center gap-1', className)}
      {...props}
    />
  ),
);
NavigationMenuList.displayName = 'NavigationMenu.List';

const NavigationMenuItem = React.forwardRef<HTMLLIElement, NavigationMenuNamespace.Item.Props>(
  (props, ref) => <BaseNavigationMenu.Item ref={ref} {...props} />,
);
NavigationMenuItem.displayName = 'NavigationMenu.Item';

const NavigationMenuTrigger = React.forwardRef<
  HTMLButtonElement,
  NavigationMenuNamespace.Trigger.Props
>(({ className, ...props }, ref) => (
  <BaseNavigationMenu.Trigger
    ref={ref}
    className={cn(
      'inline-flex h-9 items-center gap-1 rounded-md px-3 text-sm font-medium text-neutral-700 hover:bg-neutral-100',
      focusRing,
      className,
    )}
    {...props}
  />
));
NavigationMenuTrigger.displayName = 'NavigationMenu.Trigger';

const NavigationMenuLink = React.forwardRef<HTMLAnchorElement, NavigationMenuNamespace.Link.Props>(
  ({ className, ...props }, ref) => (
    <BaseNavigationMenu.Link
      ref={ref}
      className={cn(
        'inline-flex h-9 items-center rounded-md px-3 text-sm font-medium text-neutral-700 hover:bg-neutral-100',
        'data-[active]:text-brand-700',
        focusRing,
        className,
      )}
      {...props}
    />
  ),
);
NavigationMenuLink.displayName = 'NavigationMenu.Link';

const NavigationMenuIcon = React.forwardRef<HTMLSpanElement, NavigationMenuNamespace.Icon.Props>(
  ({ className, ...props }, ref) => (
    <BaseNavigationMenu.Icon ref={ref} className={cn('text-neutral-500', className)} {...props} />
  ),
);
NavigationMenuIcon.displayName = 'NavigationMenu.Icon';

const NavigationMenuBackdrop = React.forwardRef<
  HTMLDivElement,
  NavigationMenuNamespace.Backdrop.Props
>(({ className, ...props }, ref) => (
  <BaseNavigationMenu.Backdrop ref={ref} className={cn('fixed inset-0', className)} {...props} />
));
NavigationMenuBackdrop.displayName = 'NavigationMenu.Backdrop';

const NavigationMenuPopup = React.forwardRef<HTMLElement, NavigationMenuNamespace.Popup.Props>(
  ({ className, ...props }, ref) => (
    <BaseNavigationMenu.Popup
      ref={ref}
      className={cn(
        'w-[var(--popup-width)] rounded-lg border border-neutral-200 bg-neutral-0 p-4 shadow-lg',
        'transition-opacity data-[starting-style]:opacity-0 data-[ending-style]:opacity-0',
        className,
      )}
      {...props}
    />
  ),
);
NavigationMenuPopup.displayName = 'NavigationMenu.Popup';

const NavigationMenuViewport = React.forwardRef<
  HTMLDivElement,
  NavigationMenuNamespace.Viewport.Props
>(({ className, ...props }, ref) => (
  <BaseNavigationMenu.Viewport
    ref={ref}
    className={cn('relative h-[var(--popup-height)] transition-[height]', className)}
    {...props}
  />
));
NavigationMenuViewport.displayName = 'NavigationMenu.Viewport';

const NavigationMenuArrow = React.forwardRef<HTMLDivElement, NavigationMenuNamespace.Arrow.Props>(
  ({ className, ...props }, ref) => (
    <BaseNavigationMenu.Arrow ref={ref} className={cn('fill-neutral-0', className)} {...props} />
  ),
);
NavigationMenuArrow.displayName = 'NavigationMenu.Arrow';

const NavigationMenuContent = React.forwardRef<
  HTMLDivElement,
  NavigationMenuNamespace.Content.Props
>(({ className, ...props }, ref) => (
  <BaseNavigationMenu.Content
    ref={ref}
    className={cn('text-sm text-neutral-700', className)}
    {...props}
  />
));
NavigationMenuContent.displayName = 'NavigationMenu.Content';

export const NavigationMenu = {
  Root: NavigationMenuRoot,
  List: NavigationMenuList,
  Item: NavigationMenuItem,
  Trigger: NavigationMenuTrigger,
  Link: NavigationMenuLink,
  Icon: NavigationMenuIcon,
  Portal: BaseNavigationMenu.Portal,
  Backdrop: NavigationMenuBackdrop,
  Positioner: BaseNavigationMenu.Positioner,
  Popup: NavigationMenuPopup,
  Viewport: NavigationMenuViewport,
  Arrow: NavigationMenuArrow,
  Content: NavigationMenuContent,
};
