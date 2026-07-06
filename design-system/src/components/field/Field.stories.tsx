import type { Meta, StoryObj } from '@storybook/react';

import { Input } from '../input/Input';

import { Field } from './Field';

const meta: Meta<typeof Field.Root> = {
  title: 'Components/Field',
  component: Field.Root,
};

export default meta;

type Story = StoryObj<typeof Field.Root>;

export const Default: Story = {
  render: (args) => (
    <Field.Root {...args} className="w-72">
      <Field.Label>Email</Field.Label>
      <Input placeholder="you@example.com" />
      <Field.Description>We&rsquo;ll never share your email.</Field.Description>
    </Field.Root>
  ),
};

export const Invalid: Story = {
  render: (args) => (
    <Field.Root {...args} className="w-72" invalid>
      <Field.Label>Email</Field.Label>
      <Input defaultValue="not-an-email" />
      <Field.Error>Enter a valid email address.</Field.Error>
    </Field.Root>
  ),
};
