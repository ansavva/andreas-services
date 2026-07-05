import type { Select as SelectNamespace } from '@base-ui/react/select';

import * as React from 'react';
import { Select as BaseSelect } from '@base-ui/react/select';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';
import { Separator } from '../separator';

const SelectLabel = React.forwardRef<HTMLDivElement, SelectNamespace.Label.Props>(
  ({ className, ...props }, ref) => (
    <BaseSelect.Label
      ref={ref}
      className={cn('text-sm font-medium text-ink', className)}
      {...props}
    />
  ),
);
SelectLabel.displayName = 'Select.Label';

const SelectTrigger = React.forwardRef<HTMLButtonElement, SelectNamespace.Trigger.Props>(
  ({ className, ...props }, ref) => (
    <BaseSelect.Trigger
      ref={ref}
      className={cn(
        'flex h-10 w-full items-center justify-between gap-2 rounded-md border border-line',
        'bg-card px-3 text-sm text-ink',
        'data-[invalid]:border-danger',
        focusRing,
        disabledStyles,
        className,
      )}
      {...props}
    />
  ),
);
SelectTrigger.displayName = 'Select.Trigger';

const SelectValue = React.forwardRef<HTMLSpanElement, SelectNamespace.Value.Props>(
  ({ className, ...props }, ref) => (
    <BaseSelect.Value ref={ref} className={cn('truncate', className)} {...props} />
  ),
);
SelectValue.displayName = 'Select.Value';

const SelectIcon = React.forwardRef<HTMLSpanElement, SelectNamespace.Icon.Props>(
  ({ className, ...props }, ref) => (
    <BaseSelect.Icon ref={ref} className={cn('text-muted', className)} {...props}>
      <svg viewBox="0 0 16 16" fill="none" className="size-4" aria-hidden="true">
        <path
          d="M4 6l4 4 4-4"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </BaseSelect.Icon>
  ),
);
SelectIcon.displayName = 'Select.Icon';

const SelectBackdrop = React.forwardRef<HTMLDivElement, SelectNamespace.Backdrop.Props>(
  ({ className, ...props }, ref) => (
    <BaseSelect.Backdrop ref={ref} className={cn('fixed inset-0', className)} {...props} />
  ),
);
SelectBackdrop.displayName = 'Select.Backdrop';

const SelectPopup = React.forwardRef<HTMLDivElement, SelectNamespace.Popup.Props>(
  ({ className, ...props }, ref) => (
    <BaseSelect.Popup
      ref={ref}
      className={cn(
        'max-h-[min(24rem,var(--available-height))] overflow-y-auto rounded-md border border-line',
        'bg-card py-1 shadow-lg',
        'data-[starting-style]:opacity-0 data-[ending-style]:opacity-0 transition-opacity',
        className,
      )}
      {...props}
    />
  ),
);
SelectPopup.displayName = 'Select.Popup';

const SelectList = React.forwardRef<HTMLDivElement, SelectNamespace.List.Props>(
  ({ className, ...props }, ref) => (
    <BaseSelect.List ref={ref} className={cn('flex flex-col', className)} {...props} />
  ),
);
SelectList.displayName = 'Select.List';

const SelectGroup = React.forwardRef<HTMLDivElement, SelectNamespace.Group.Props>(
  ({ className, ...props }, ref) => (
    <BaseSelect.Group ref={ref} className={cn('flex flex-col', className)} {...props} />
  ),
);
SelectGroup.displayName = 'Select.Group';

const SelectGroupLabel = React.forwardRef<HTMLDivElement, SelectNamespace.GroupLabel.Props>(
  ({ className, ...props }, ref) => (
    <BaseSelect.GroupLabel
      ref={ref}
      className={cn('px-3 py-1.5 text-xs font-semibold uppercase text-muted', className)}
      {...props}
    />
  ),
);
SelectGroupLabel.displayName = 'Select.GroupLabel';

const SelectItem = React.forwardRef<HTMLDivElement, SelectNamespace.Item.Props>(
  ({ className, ...props }, ref) => (
    <BaseSelect.Item
      ref={ref}
      className={cn(
        'flex cursor-default items-center justify-between gap-2 px-3 py-2 text-sm text-ink',
        'data-[highlighted]:bg-surface-alt data-[highlighted]:text-ink',
        disabledStyles,
        className,
      )}
      {...props}
    />
  ),
);
SelectItem.displayName = 'Select.Item';

const SelectItemText = React.forwardRef<HTMLDivElement, SelectNamespace.ItemText.Props>(
  ({ className, ...props }, ref) => (
    <BaseSelect.ItemText ref={ref} className={cn('truncate', className)} {...props} />
  ),
);
SelectItemText.displayName = 'Select.ItemText';

const SelectItemIndicator = React.forwardRef<HTMLSpanElement, SelectNamespace.ItemIndicator.Props>(
  ({ className, ...props }, ref) => (
    <BaseSelect.ItemIndicator ref={ref} className={cn('flex text-primary', className)} {...props}>
      <svg viewBox="0 0 16 16" fill="none" className="size-3.5" aria-hidden="true">
        <path
          d="M3.5 8.5L6.5 11.5L12.5 4.5"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </BaseSelect.ItemIndicator>
  ),
);
SelectItemIndicator.displayName = 'Select.ItemIndicator';

const scrollArrowStyles = 'flex h-6 items-center justify-center text-muted';

const SelectScrollUpArrow = React.forwardRef<HTMLDivElement, SelectNamespace.ScrollUpArrow.Props>(
  ({ className, ...props }, ref) => (
    <BaseSelect.ScrollUpArrow ref={ref} className={cn(scrollArrowStyles, className)} {...props} />
  ),
);
SelectScrollUpArrow.displayName = 'Select.ScrollUpArrow';

const SelectScrollDownArrow = React.forwardRef<
  HTMLDivElement,
  SelectNamespace.ScrollDownArrow.Props
>(({ className, ...props }, ref) => (
  <BaseSelect.ScrollDownArrow ref={ref} className={cn(scrollArrowStyles, className)} {...props} />
));
SelectScrollDownArrow.displayName = 'Select.ScrollDownArrow';

export const Select = {
  Root: BaseSelect.Root,
  Portal: BaseSelect.Portal,
  Positioner: BaseSelect.Positioner,
  Arrow: BaseSelect.Arrow,
  Label: SelectLabel,
  Trigger: SelectTrigger,
  Value: SelectValue,
  Icon: SelectIcon,
  Backdrop: SelectBackdrop,
  Popup: SelectPopup,
  List: SelectList,
  Group: SelectGroup,
  GroupLabel: SelectGroupLabel,
  Item: SelectItem,
  ItemText: SelectItemText,
  ItemIndicator: SelectItemIndicator,
  ScrollUpArrow: SelectScrollUpArrow,
  ScrollDownArrow: SelectScrollDownArrow,
  Separator,
};
