import type { Menu as MenuNamespace } from '@base-ui/react/menu';

import * as React from 'react';
import { Menu as BaseMenu } from '@base-ui/react/menu';

import { cn } from '../../lib/cn';
import { disabledStyles } from '../../lib/styles';
import { Separator } from '../separator';

const menuItemStyles = cn(
  'flex cursor-default items-center gap-2 px-3 py-2 text-sm text-ink outline-none',
  'data-[highlighted]:bg-surface-alt data-[highlighted]:text-ink',
  disabledStyles,
);

const MenuBackdrop = React.forwardRef<HTMLDivElement, MenuNamespace.Backdrop.Props>(
  ({ className, ...props }, ref) => (
    <BaseMenu.Backdrop ref={ref} className={cn('fixed inset-0', className)} {...props} />
  ),
);
MenuBackdrop.displayName = 'Menu.Backdrop';

const MenuPopup = React.forwardRef<HTMLDivElement, MenuNamespace.Popup.Props>(
  ({ className, ...props }, ref) => (
    <BaseMenu.Popup
      ref={ref}
      className={cn(
        'min-w-[10rem] rounded-md border border-line bg-card py-1 shadow-lg',
        'transition-opacity data-[starting-style]:opacity-0 data-[ending-style]:opacity-0',
        className,
      )}
      {...props}
    />
  ),
);
MenuPopup.displayName = 'Menu.Popup';

const MenuArrow = React.forwardRef<HTMLDivElement, MenuNamespace.Arrow.Props>(
  ({ className, ...props }, ref) => (
    <BaseMenu.Arrow ref={ref} className={cn('fill-card', className)} {...props} />
  ),
);
MenuArrow.displayName = 'Menu.Arrow';

const MenuItem = React.forwardRef<HTMLElement, MenuNamespace.Item.Props>(
  ({ className, ...props }, ref) => (
    <BaseMenu.Item ref={ref} className={cn(menuItemStyles, className)} {...props} />
  ),
);
MenuItem.displayName = 'Menu.Item';

const MenuLinkItem = React.forwardRef<Element, MenuNamespace.LinkItem.Props>(
  ({ className, ...props }, ref) => (
    <BaseMenu.LinkItem ref={ref} className={cn(menuItemStyles, className)} {...props} />
  ),
);
MenuLinkItem.displayName = 'Menu.LinkItem';

const MenuSubmenuTrigger = React.forwardRef<HTMLElement, MenuNamespace.SubmenuTrigger.Props>(
  ({ className, ...props }, ref) => (
    <BaseMenu.SubmenuTrigger
      ref={ref}
      className={cn(menuItemStyles, 'justify-between', className)}
      {...props}
    />
  ),
);
MenuSubmenuTrigger.displayName = 'Menu.SubmenuTrigger';

const MenuCheckboxItem = React.forwardRef<HTMLElement, MenuNamespace.CheckboxItem.Props>(
  ({ className, ...props }, ref) => (
    <BaseMenu.CheckboxItem ref={ref} className={cn(menuItemStyles, className)} {...props} />
  ),
);
MenuCheckboxItem.displayName = 'Menu.CheckboxItem';

const MenuRadioItem = React.forwardRef<HTMLElement, MenuNamespace.RadioItem.Props>(
  ({ className, ...props }, ref) => (
    <BaseMenu.RadioItem ref={ref} className={cn(menuItemStyles, className)} {...props} />
  ),
);
MenuRadioItem.displayName = 'Menu.RadioItem';

const itemIndicatorStyles = 'flex w-4 text-primary';

const MenuCheckboxItemIndicator = React.forwardRef<
  HTMLSpanElement,
  MenuNamespace.CheckboxItemIndicator.Props
>(({ className, ...props }, ref) => (
  <BaseMenu.CheckboxItemIndicator
    ref={ref}
    className={cn(itemIndicatorStyles, className)}
    {...props}
  >
    <svg viewBox="0 0 16 16" fill="none" className="size-3.5" aria-hidden="true">
      <path
        d="M3.5 8.5L6.5 11.5L12.5 4.5"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  </BaseMenu.CheckboxItemIndicator>
));
MenuCheckboxItemIndicator.displayName = 'Menu.CheckboxItemIndicator';

const MenuRadioItemIndicator = React.forwardRef<
  HTMLSpanElement,
  MenuNamespace.RadioItemIndicator.Props
>(({ className, ...props }, ref) => (
  <BaseMenu.RadioItemIndicator ref={ref} className={cn(itemIndicatorStyles, className)} {...props}>
    <svg viewBox="0 0 16 16" fill="currentColor" className="size-2">
      <circle cx="8" cy="8" r="4" />
    </svg>
  </BaseMenu.RadioItemIndicator>
));
MenuRadioItemIndicator.displayName = 'Menu.RadioItemIndicator';

const MenuGroup = React.forwardRef<HTMLDivElement, MenuNamespace.Group.Props>(
  ({ className, ...props }, ref) => (
    <BaseMenu.Group ref={ref} className={cn('flex flex-col', className)} {...props} />
  ),
);
MenuGroup.displayName = 'Menu.Group';

const MenuGroupLabel = React.forwardRef<HTMLDivElement, MenuNamespace.GroupLabel.Props>(
  ({ className, ...props }, ref) => (
    <BaseMenu.GroupLabel
      ref={ref}
      className={cn('px-3 py-1.5 text-xs font-semibold uppercase text-muted', className)}
      {...props}
    />
  ),
);
MenuGroupLabel.displayName = 'Menu.GroupLabel';

export const Menu = {
  Root: BaseMenu.Root,
  Trigger: BaseMenu.Trigger,
  Portal: BaseMenu.Portal,
  Positioner: BaseMenu.Positioner,
  Viewport: BaseMenu.Viewport,
  Backdrop: MenuBackdrop,
  Popup: MenuPopup,
  Arrow: MenuArrow,
  Item: MenuItem,
  LinkItem: MenuLinkItem,
  SubmenuRoot: BaseMenu.SubmenuRoot,
  SubmenuTrigger: MenuSubmenuTrigger,
  CheckboxItem: MenuCheckboxItem,
  CheckboxItemIndicator: MenuCheckboxItemIndicator,
  RadioGroup: BaseMenu.RadioGroup,
  RadioItem: MenuRadioItem,
  RadioItemIndicator: MenuRadioItemIndicator,
  Group: MenuGroup,
  GroupLabel: MenuGroupLabel,
  Separator,
  Handle: BaseMenu.Handle,
  createHandle: BaseMenu.createHandle,
};
