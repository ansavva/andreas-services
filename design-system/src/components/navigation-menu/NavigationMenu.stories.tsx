import type { Meta, StoryObj } from '@storybook/react';

import { NavigationMenu } from './NavigationMenu';

const meta: Meta<typeof NavigationMenu.Root> = {
  title: 'Components/NavigationMenu',
  component: NavigationMenu.Root,
};

export default meta;

type Story = StoryObj<typeof NavigationMenu.Root>;

export const Default: Story = {
  render: (args) => (
    <NavigationMenu.Root {...args}>
      <NavigationMenu.List>
        <NavigationMenu.Item>
          <NavigationMenu.Trigger>Products</NavigationMenu.Trigger>
          <NavigationMenu.Content>
            <p className="text-sm text-muted">Explore our product lineup.</p>
          </NavigationMenu.Content>
        </NavigationMenu.Item>
        <NavigationMenu.Item>
          <NavigationMenu.Link href="#pricing">Pricing</NavigationMenu.Link>
        </NavigationMenu.Item>
      </NavigationMenu.List>
      <NavigationMenu.Portal>
        <NavigationMenu.Positioner>
          <NavigationMenu.Popup>
            <NavigationMenu.Viewport />
          </NavigationMenu.Popup>
        </NavigationMenu.Positioner>
      </NavigationMenu.Portal>
    </NavigationMenu.Root>
  ),
};
