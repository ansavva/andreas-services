import type { Meta, StoryObj } from '@storybook/react';

import { Button } from '../button/Button';

import { Tooltip } from './Tooltip';

const meta: Meta<typeof Tooltip.Root> = {
  title: 'Components/Tooltip',
  component: Tooltip.Root,
};

export default meta;

type Story = StoryObj<typeof Tooltip.Root>;

export const Default: Story = {
  render: (args) => (
    <Tooltip.Provider>
      <Tooltip.Root {...args}>
        <Tooltip.Trigger render={<Button intent="secondary">Hover me</Button>} />
        <Tooltip.Portal>
          <Tooltip.Positioner sideOffset={8}>
            <Tooltip.Popup>Saved to your library</Tooltip.Popup>
          </Tooltip.Positioner>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  ),
};
