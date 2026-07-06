import type { Meta, StoryObj } from '@storybook/react';

import { Progress } from './Progress';

const meta: Meta<typeof Progress.Root> = {
  title: 'Components/Progress',
  component: Progress.Root,
};

export default meta;

type Story = StoryObj<typeof Progress.Root>;

export const Default: Story = {
  render: (args) => (
    <Progress.Root {...args} value={60} className="w-64">
      <div className="flex justify-between">
        <Progress.Label>Uploading</Progress.Label>
        <Progress.Value />
      </div>
      <Progress.Track>
        <Progress.Indicator />
      </Progress.Track>
    </Progress.Root>
  ),
};
