import type { Meta, StoryObj } from '@storybook/react';

import { Button } from '../button/Button';
import { Field } from '../field/Field';
import { Input } from '../input/Input';

import { Form } from './Form';

const meta: Meta<typeof Form> = {
  title: 'Components/Form',
  component: Form,
};

export default meta;

type Story = StoryObj<typeof Form>;

export const Default: Story = {
  render: () => (
    <Form className="w-72" onSubmit={(event) => event.preventDefault()}>
      <Field.Root name="email">
        <Field.Label>Email</Field.Label>
        <Input required placeholder="you@example.com" />
      </Field.Root>
      <Button type="submit">Submit</Button>
    </Form>
  ),
};
