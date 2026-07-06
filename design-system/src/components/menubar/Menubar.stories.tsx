import type { Meta, StoryObj } from '@storybook/react';

import { Menu } from '../menu/Menu';

import { Menubar } from './Menubar';

const meta: Meta<typeof Menubar> = {
  title: 'Components/Menubar',
  component: Menubar,
};

export default meta;

type Story = StoryObj<typeof Menubar>;

export const Default: Story = {
  render: (args) => (
    <Menubar {...args}>
      <Menu.Root>
        <Menu.Trigger className="rounded px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-alt">
          File
        </Menu.Trigger>
        <Menu.Portal>
          <Menu.Positioner sideOffset={4}>
            <Menu.Popup>
              <Menu.Item>New</Menu.Item>
              <Menu.Item>Open</Menu.Item>
            </Menu.Popup>
          </Menu.Positioner>
        </Menu.Portal>
      </Menu.Root>
      <Menu.Root>
        <Menu.Trigger className="rounded px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-alt">
          Edit
        </Menu.Trigger>
        <Menu.Portal>
          <Menu.Positioner sideOffset={4}>
            <Menu.Popup>
              <Menu.Item>Undo</Menu.Item>
              <Menu.Item>Redo</Menu.Item>
            </Menu.Popup>
          </Menu.Positioner>
        </Menu.Portal>
      </Menu.Root>
    </Menubar>
  ),
};
