import type { Combobox as ComboboxNamespace } from '@base-ui/react/combobox';

import * as React from 'react';
import { Combobox as BaseCombobox } from '@base-ui/react/combobox';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';
import { Separator } from '../separator';

const ComboboxLabel = React.forwardRef<HTMLDivElement, ComboboxNamespace.Label.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Label
      ref={ref}
      className={cn('text-sm font-medium text-ink', className)}
      {...props}
    />
  ),
);
ComboboxLabel.displayName = 'Combobox.Label';

const ComboboxInputGroup = React.forwardRef<HTMLDivElement, ComboboxNamespace.InputGroup.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.InputGroup
      ref={ref}
      className={cn(
        'flex h-10 items-center gap-1.5 rounded-md border border-line bg-card px-3',
        'data-[invalid]:border-danger',
        focusRing,
        disabledStyles,
        className,
      )}
      {...props}
    />
  ),
);
ComboboxInputGroup.displayName = 'Combobox.InputGroup';

const ComboboxInput = React.forwardRef<HTMLInputElement, ComboboxNamespace.Input.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Input
      ref={ref}
      className={cn(
        'w-full min-w-0 flex-1 bg-transparent text-sm text-ink placeholder:text-muted focus:outline-none',
        className,
      )}
      {...props}
    />
  ),
);
ComboboxInput.displayName = 'Combobox.Input';

const ComboboxTrigger = React.forwardRef<HTMLButtonElement, ComboboxNamespace.Trigger.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Trigger
      ref={ref}
      className={cn('flex items-center text-muted', className)}
      {...props}
    />
  ),
);
ComboboxTrigger.displayName = 'Combobox.Trigger';

const ComboboxIcon = React.forwardRef<HTMLSpanElement, ComboboxNamespace.Icon.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Icon ref={ref} className={cn('text-muted', className)} {...props} />
  ),
);
ComboboxIcon.displayName = 'Combobox.Icon';

const ComboboxClear = React.forwardRef<HTMLButtonElement, ComboboxNamespace.Clear.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Clear
      ref={ref}
      className={cn('flex text-muted hover:text-ink', className)}
      {...props}
    />
  ),
);
ComboboxClear.displayName = 'Combobox.Clear';

const ComboboxChips = React.forwardRef<HTMLDivElement, ComboboxNamespace.Chips.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Chips
      ref={ref}
      className={cn('flex flex-wrap items-center gap-1', className)}
      {...props}
    />
  ),
);
ComboboxChips.displayName = 'Combobox.Chips';

const ComboboxChip = React.forwardRef<HTMLDivElement, ComboboxNamespace.Chip.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Chip
      ref={ref}
      className={cn(
        'flex items-center gap-1 rounded bg-surface-alt px-2 py-0.5 text-sm text-ink',
        className,
      )}
      {...props}
    />
  ),
);
ComboboxChip.displayName = 'Combobox.Chip';

const ComboboxChipRemove = React.forwardRef<HTMLButtonElement, ComboboxNamespace.ChipRemove.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.ChipRemove
      ref={ref}
      className={cn('text-muted hover:text-ink', className)}
      {...props}
    />
  ),
);
ComboboxChipRemove.displayName = 'Combobox.ChipRemove';

const ComboboxBackdrop = React.forwardRef<HTMLDivElement, ComboboxNamespace.Backdrop.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Backdrop ref={ref} className={cn('fixed inset-0', className)} {...props} />
  ),
);
ComboboxBackdrop.displayName = 'Combobox.Backdrop';

const ComboboxPopup = React.forwardRef<HTMLDivElement, ComboboxNamespace.Popup.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Popup
      ref={ref}
      className={cn(
        'max-h-[min(24rem,var(--available-height))] overflow-y-auto rounded-md border border-line',
        'bg-card py-1 shadow-lg',
        'transition-opacity data-[starting-style]:opacity-0 data-[ending-style]:opacity-0',
        className,
      )}
      {...props}
    />
  ),
);
ComboboxPopup.displayName = 'Combobox.Popup';

const ComboboxArrow = React.forwardRef<HTMLDivElement, ComboboxNamespace.Arrow.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Arrow ref={ref} className={cn('fill-card', className)} {...props} />
  ),
);
ComboboxArrow.displayName = 'Combobox.Arrow';

const ComboboxList = React.forwardRef<HTMLDivElement, ComboboxNamespace.List.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.List ref={ref} className={cn('flex flex-col', className)} {...props} />
  ),
);
ComboboxList.displayName = 'Combobox.List';

const ComboboxRow = React.forwardRef<HTMLDivElement, ComboboxNamespace.Row.Props>((props, ref) => (
  <BaseCombobox.Row ref={ref} {...props} />
));
ComboboxRow.displayName = 'Combobox.Row';

const ComboboxStatus = React.forwardRef<HTMLDivElement, ComboboxNamespace.Status.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Status
      ref={ref}
      className={cn('px-3 py-2 text-sm text-muted', className)}
      {...props}
    />
  ),
);
ComboboxStatus.displayName = 'Combobox.Status';

const ComboboxEmpty = React.forwardRef<HTMLDivElement, ComboboxNamespace.Empty.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Empty
      ref={ref}
      className={cn('px-3 py-2 text-sm text-muted', className)}
      {...props}
    />
  ),
);
ComboboxEmpty.displayName = 'Combobox.Empty';

const ComboboxGroup = React.forwardRef<HTMLDivElement, ComboboxNamespace.Group.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Group ref={ref} className={cn('flex flex-col', className)} {...props} />
  ),
);
ComboboxGroup.displayName = 'Combobox.Group';

const ComboboxGroupLabel = React.forwardRef<HTMLDivElement, ComboboxNamespace.GroupLabel.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.GroupLabel
      ref={ref}
      className={cn('px-3 py-1.5 text-xs font-semibold uppercase text-muted', className)}
      {...props}
    />
  ),
);
ComboboxGroupLabel.displayName = 'Combobox.GroupLabel';

const ComboboxItem = React.forwardRef<HTMLDivElement, ComboboxNamespace.Item.Props>(
  ({ className, ...props }, ref) => (
    <BaseCombobox.Item
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
ComboboxItem.displayName = 'Combobox.Item';

const ComboboxItemIndicator = React.forwardRef<
  HTMLSpanElement,
  ComboboxNamespace.ItemIndicator.Props
>(({ className, ...props }, ref) => (
  <BaseCombobox.ItemIndicator ref={ref} className={cn('flex text-primary', className)} {...props}>
    <svg viewBox="0 0 16 16" fill="none" className="size-3.5" aria-hidden="true">
      <path
        d="M3.5 8.5L6.5 11.5L12.5 4.5"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  </BaseCombobox.ItemIndicator>
));
ComboboxItemIndicator.displayName = 'Combobox.ItemIndicator';

export const Combobox = {
  Root: BaseCombobox.Root,
  Label: ComboboxLabel,
  Value: BaseCombobox.Value,
  InputGroup: ComboboxInputGroup,
  Input: ComboboxInput,
  Trigger: ComboboxTrigger,
  Icon: ComboboxIcon,
  Clear: ComboboxClear,
  Chips: ComboboxChips,
  Chip: ComboboxChip,
  ChipRemove: ComboboxChipRemove,
  Portal: BaseCombobox.Portal,
  Backdrop: ComboboxBackdrop,
  Positioner: BaseCombobox.Positioner,
  Popup: ComboboxPopup,
  Arrow: ComboboxArrow,
  List: ComboboxList,
  Row: ComboboxRow,
  Collection: BaseCombobox.Collection,
  Status: ComboboxStatus,
  Empty: ComboboxEmpty,
  Group: ComboboxGroup,
  GroupLabel: ComboboxGroupLabel,
  Item: ComboboxItem,
  ItemIndicator: ComboboxItemIndicator,
  Separator,
  useFilter: BaseCombobox.useFilter,
  useFilteredItems: BaseCombobox.useFilteredItems,
};
