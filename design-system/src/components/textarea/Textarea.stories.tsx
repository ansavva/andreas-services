import type { Meta, StoryObj } from '@storybook/react';

import { Textarea } from './Textarea';

const meta: Meta<typeof Textarea> = {
  title: 'Components/Textarea',
  component: Textarea,
  args: {
    placeholder: 'Add a few thoughtful gift ideas…',
  },
};

export default meta;

type Story = StoryObj<typeof Textarea>;

export const Default: Story = {};

export const WithValue: Story = {
  args: { defaultValue: 'A book about architecture\nA warm pair of gloves' },
};

export const Invalid: Story = {
  args: { 'aria-invalid': true, defaultValue: 'Please add more detail.' },
};

export const Disabled: Story = {
  args: { disabled: true, defaultValue: 'This field is unavailable.' },
};
