import type { Meta, StoryObj } from '@storybook/react';

import { Field } from '../field/Field';
import { Input } from '../input/Input';

import { Fieldset } from './Fieldset';

const meta: Meta<typeof Fieldset.Root> = {
  title: 'Components/Fieldset',
  component: Fieldset.Root,
};

export default meta;

type Story = StoryObj<typeof Fieldset.Root>;

export const Default: Story = {
  render: (args) => (
    <Fieldset.Root {...args} className="w-80">
      <Fieldset.Legend>Contact details</Fieldset.Legend>
      <Field.Root>
        <Field.Label>Name</Field.Label>
        <Input placeholder="Jane Doe" />
      </Field.Root>
      <Field.Root>
        <Field.Label>Email</Field.Label>
        <Input placeholder="you@example.com" />
      </Field.Root>
    </Fieldset.Root>
  ),
};
