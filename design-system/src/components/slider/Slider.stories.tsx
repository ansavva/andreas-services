import type { Meta, StoryObj } from '@storybook/react';

import { Slider } from './Slider';

const meta: Meta<typeof Slider.Root> = {
  title: 'Components/Slider',
  component: Slider.Root,
};

export default meta;

type Story = StoryObj<typeof Slider.Root>;

export const Default: Story = {
  render: (args) => (
    <Slider.Root {...args} defaultValue={40} className="w-64">
      <div className="flex justify-between">
        <Slider.Label>Volume</Slider.Label>
        <Slider.Value />
      </div>
      <Slider.Control>
        <Slider.Track>
          <Slider.Indicator />
          <Slider.Thumb />
        </Slider.Track>
      </Slider.Control>
    </Slider.Root>
  ),
};
