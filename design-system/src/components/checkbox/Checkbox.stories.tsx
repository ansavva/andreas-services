import type { Meta, StoryObj } from '@storybook/react';

import { Field } from '../field/Field';

import { Checkbox } from './Checkbox';

const meta: Meta<typeof Checkbox.Root> = {
  title: 'Components/Checkbox',
  component: Checkbox.Root,
};

export default meta;

type Story = StoryObj<typeof Checkbox.Root>;

export const Default: Story = {
  render: (args) => (
    <Field.Item>
      <Checkbox.Root {...args} defaultChecked>
        <Checkbox.Indicator />
      </Checkbox.Root>
      <Field.Label>Accept terms and conditions</Field.Label>
    </Field.Item>
  ),
};

export const Indeterminate: Story = {
  render: (args) => (
    <Checkbox.Root {...args} indeterminate aria-label="Select all">
      <Checkbox.Indicator />
    </Checkbox.Root>
  ),
};

export const Disabled: Story = {
  render: (args) => (
    <Checkbox.Root {...args} disabled aria-label="Disabled checkbox">
      <Checkbox.Indicator />
    </Checkbox.Root>
  ),
};
