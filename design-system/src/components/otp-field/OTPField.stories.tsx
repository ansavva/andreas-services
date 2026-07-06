import type { Meta, StoryObj } from '@storybook/react';

import { OTPField } from './OTPField';

const meta: Meta<typeof OTPField.Root> = {
  title: 'Components/OTPField',
  component: OTPField.Root,
};

export default meta;

type Story = StoryObj<typeof OTPField.Root>;

export const Default: Story = {
  render: (args) => (
    <OTPField.Root {...args} length={6} aria-label="Verification code">
      {Array.from({ length: 6 }, (_, i) => (
        <OTPField.Input key={i} />
      ))}
    </OTPField.Root>
  ),
};
