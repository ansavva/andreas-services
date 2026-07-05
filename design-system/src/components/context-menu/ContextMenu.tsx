import { ContextMenu as BaseContextMenu } from '@base-ui/react/context-menu';

import { Menu } from '../menu/Menu';

// ContextMenu re-exports Menu's own parts for everything except Root/Trigger,
// so we reuse the already-styled Menu components directly.
export const ContextMenu = {
  Root: BaseContextMenu.Root,
  Trigger: BaseContextMenu.Trigger,
  Portal: Menu.Portal,
  Positioner: Menu.Positioner,
  Backdrop: Menu.Backdrop,
  Popup: Menu.Popup,
  Arrow: Menu.Arrow,
  Item: Menu.Item,
  LinkItem: Menu.LinkItem,
  SubmenuRoot: Menu.SubmenuRoot,
  SubmenuTrigger: Menu.SubmenuTrigger,
  CheckboxItem: Menu.CheckboxItem,
  CheckboxItemIndicator: Menu.CheckboxItemIndicator,
  RadioGroup: Menu.RadioGroup,
  RadioItem: Menu.RadioItem,
  RadioItemIndicator: Menu.RadioItemIndicator,
  Group: Menu.Group,
  GroupLabel: Menu.GroupLabel,
  Separator: Menu.Separator,
};
