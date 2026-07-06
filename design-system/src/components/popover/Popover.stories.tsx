import type { Meta, StoryObj } from '@storybook/react';

import { Button } from '../button/Button';

import { Popover } from './Popover';

const meta: Meta<typeof Popover.Root> = {
  title: 'Components/Popover',
  component: Popover.Root,
};

export default meta;

type Story = StoryObj<typeof Popover.Root>;

export const Default: Story = {
  render: (args) => (
    <Popover.Root {...args}>
      <Popover.Trigger render={<Button intent="secondary">View details</Button>} />
      <Popover.Portal>
        <Popover.Positioner sideOffset={8}>
          <Popover.Popup>
            <Popover.Title>Storage</Popover.Title>
            <Popover.Description>You&rsquo;re using 6.2 GB of your 10 GB plan.</Popover.Description>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  ),
};
