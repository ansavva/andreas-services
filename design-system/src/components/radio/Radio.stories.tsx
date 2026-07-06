import type { Meta, StoryObj } from '@storybook/react';

import { Field } from '../field/Field';

import { Radio, RadioGroup } from './Radio';

const meta: Meta<typeof RadioGroup> = {
  title: 'Components/Radio',
  component: RadioGroup,
};

export default meta;

type Story = StoryObj<typeof RadioGroup>;

const plans = ['free', 'pro', 'enterprise'];

export const Default: Story = {
  render: (args) => (
    <RadioGroup {...args} defaultValue="pro" aria-label="Plan">
      {plans.map((plan) => (
        <Field.Item key={plan}>
          <Radio.Root value={plan}>
            <Radio.Indicator />
          </Radio.Root>
          <Field.Label className="capitalize">{plan}</Field.Label>
        </Field.Item>
      ))}
    </RadioGroup>
  ),
};
