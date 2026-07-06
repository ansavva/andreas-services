import type { Meta, StoryObj } from '@storybook/react';

import { Button } from '../button/Button';

import { Drawer } from './Drawer';

const meta: Meta<typeof Drawer.Root> = {
  title: 'Components/Drawer',
  component: Drawer.Root,
};

export default meta;

type Story = StoryObj<typeof Drawer.Root>;

export const Default: Story = {
  render: (args) => (
    <Drawer.Root {...args}>
      <Drawer.Trigger render={<Button intent="secondary">Open menu</Button>} />
      <Drawer.Portal>
        <Drawer.Backdrop />
        <Drawer.Viewport>
          <Drawer.Popup>
            <Drawer.Content>
              <Drawer.Title>Menu</Drawer.Title>
              <Drawer.Description>Navigate the app from here.</Drawer.Description>
              <div className="mt-4">
                <Drawer.Close render={<Button intent="ghost">Close</Button>} />
              </div>
            </Drawer.Content>
          </Drawer.Popup>
        </Drawer.Viewport>
      </Drawer.Portal>
    </Drawer.Root>
  ),
};
