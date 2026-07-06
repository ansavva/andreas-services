import type { Autocomplete as AutocompleteNamespace } from '@base-ui/react/autocomplete';

import * as React from 'react';
import { Autocomplete as BaseAutocomplete } from '@base-ui/react/autocomplete';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';
import { Combobox } from '../combobox/Combobox';

const AutocompleteInputGroup = React.forwardRef<
  HTMLDivElement,
  AutocompleteNamespace.InputGroup.Props
>(({ className, ...props }, ref) => (
  <BaseAutocomplete.InputGroup
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
));
AutocompleteInputGroup.displayName = 'Autocomplete.InputGroup';

const AutocompleteTrigger = React.forwardRef<
  HTMLButtonElement,
  AutocompleteNamespace.Trigger.Props
>(({ className, ...props }, ref) => (
  <BaseAutocomplete.Trigger
    ref={ref}
    className={cn('flex items-center text-muted', className)}
    {...props}
  />
));
AutocompleteTrigger.displayName = 'Autocomplete.Trigger';

const AutocompleteItem = React.forwardRef<HTMLDivElement, AutocompleteNamespace.Item.Props>(
  ({ className, ...props }, ref) => (
    <BaseAutocomplete.Item
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
AutocompleteItem.displayName = 'Autocomplete.Item';

// Autocomplete re-exports most of Combobox's own parts (Input, Icon, Clear,
// List, Status, Portal, Backdrop, Positioner, Popup, Arrow, Group, GroupLabel,
// Row, Collection, Empty, Separator) — reuse the already-styled versions.
export const Autocomplete = {
  Root: BaseAutocomplete.Root,
  Value: BaseAutocomplete.Value,
  Trigger: AutocompleteTrigger,
  Input: Combobox.Input,
  InputGroup: AutocompleteInputGroup,
  Icon: Combobox.Icon,
  Clear: Combobox.Clear,
  Portal: Combobox.Portal,
  Backdrop: Combobox.Backdrop,
  Positioner: Combobox.Positioner,
  Popup: Combobox.Popup,
  Arrow: Combobox.Arrow,
  List: Combobox.List,
  Row: Combobox.Row,
  Collection: Combobox.Collection,
  Status: Combobox.Status,
  Empty: Combobox.Empty,
  Group: Combobox.Group,
  GroupLabel: Combobox.GroupLabel,
  Item: AutocompleteItem,
  Separator: Combobox.Separator,
  useFilter: BaseAutocomplete.useFilter,
  useFilteredItems: BaseAutocomplete.useFilteredItems,
};
