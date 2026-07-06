import type { Meta, StoryObj } from '@storybook/react';

import { Field } from '../field/Field';

import { Switch } from './Switch';

const meta: Meta<typeof Switch.Root> = {
  title: 'Components/Switch',
  component: Switch.Root,
};

export default meta;

type Story = StoryObj<typeof Switch.Root>;

export const Default: Story = {
  render: (args) => (
    <Field.Root>
      <Field.Item>
        <Switch.Root {...args} defaultChecked>
          <Switch.Thumb />
        </Switch.Root>
        <Field.Label>Enable notifications</Field.Label>
      </Field.Item>
    </Field.Root>
  ),
};

export const Disabled: Story = {
  render: (args) => (
    <Switch.Root {...args} disabled aria-label="Disabled switch">
      <Switch.Thumb />
    </Switch.Root>
  ),
};
