import type { Meta, StoryObj } from '@storybook/react';

import { NumberField } from './NumberField';

const meta: Meta<typeof NumberField.Root> = {
  title: 'Components/NumberField',
  component: NumberField.Root,
  args: {
    defaultValue: 10,
    min: 0,
    max: 100,
  },
};

export default meta;

type Story = StoryObj<typeof NumberField.Root>;

export const Default: Story = {
  render: (args) => (
    <NumberField.Root {...args} aria-label="Quantity">
      <NumberField.Group>
        <NumberField.Decrement>−</NumberField.Decrement>
        <NumberField.Input />
        <NumberField.Increment>+</NumberField.Increment>
      </NumberField.Group>
    </NumberField.Root>
  ),
};
