import type { Meta, StoryObj } from '@storybook/react';

import { Meter } from './Meter';

const meta: Meta<typeof Meter.Root> = {
  title: 'Components/Meter',
  component: Meter.Root,
};

export default meta;

type Story = StoryObj<typeof Meter.Root>;

export const Default: Story = {
  render: (args) => (
    <Meter.Root {...args} value={75} max={100} className="w-64">
      <div className="flex justify-between">
        <Meter.Label>Disk usage</Meter.Label>
        <Meter.Value />
      </div>
      <Meter.Track>
        <Meter.Indicator />
      </Meter.Track>
    </Meter.Root>
  ),
};
