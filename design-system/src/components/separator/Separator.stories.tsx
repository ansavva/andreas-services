import type { Meta, StoryObj } from '@storybook/react';

import { Separator } from './Separator';

const meta: Meta<typeof Separator> = {
  title: 'Components/Separator',
  component: Separator,
};

export default meta;

type Story = StoryObj<typeof Separator>;

export const Horizontal: Story = {
  render: (args) => (
    <div className="w-64">
      <p className="text-sm text-ink">Above</p>
      <Separator {...args} className="my-3" />
      <p className="text-sm text-ink">Below</p>
    </div>
  ),
};

export const Vertical: Story = {
  render: (args) => (
    <div className="flex h-8 items-center gap-3">
      <span className="text-sm text-ink">Left</span>
      <Separator {...args} orientation="vertical" />
      <span className="text-sm text-ink">Right</span>
    </div>
  ),
};
