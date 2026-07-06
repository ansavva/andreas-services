import type { Meta, StoryObj } from '@storybook/react';

import { Checkbox } from '../checkbox/Checkbox';
import { Field } from '../field/Field';

import { CheckboxGroup } from './CheckboxGroup';

const meta: Meta<typeof CheckboxGroup> = {
  title: 'Components/CheckboxGroup',
  component: CheckboxGroup,
};

export default meta;

type Story = StoryObj<typeof CheckboxGroup>;

const labels = ['Email', 'SMS', 'Push notifications'];

export const Default: Story = {
  render: (args) => (
    <CheckboxGroup {...args} defaultValue={['email']} aria-label="Notification channels">
      {labels.map((label) => (
        <Field.Item key={label}>
          <Checkbox.Root name={label.toLowerCase()}>
            <Checkbox.Indicator />
          </Checkbox.Root>
          <Field.Label>{label}</Field.Label>
        </Field.Item>
      ))}
    </CheckboxGroup>
  ),
};
