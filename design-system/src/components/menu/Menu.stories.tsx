import type { Meta, StoryObj } from '@storybook/react';

import { Button } from '../button/Button';

import { Menu } from './Menu';

const meta: Meta<typeof Menu.Root> = {
  title: 'Components/Menu',
  component: Menu.Root,
};

export default meta;

type Story = StoryObj<typeof Menu.Root>;

export const Default: Story = {
  render: (args) => (
    <Menu.Root {...args}>
      <Menu.Trigger render={<Button intent="secondary">Actions</Button>} />
      <Menu.Portal>
        <Menu.Positioner sideOffset={4}>
          <Menu.Popup>
            <Menu.Item>Edit</Menu.Item>
            <Menu.Item>Duplicate</Menu.Item>
            <Menu.Separator />
            <Menu.Item>Delete</Menu.Item>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  ),
};
