import type { Meta, StoryObj } from '@storybook/react';

import { Button } from './Button';

const meta: Meta<typeof Button> = {
  title: 'Components/Button',
  component: Button,
  args: {
    children: 'Button',
    intent: 'primary',
    size: 'md',
  },
  argTypes: {
    intent: {
      control: 'select',
      options: ['primary', 'secondary', 'danger', 'ghost'],
    },
    size: {
      control: 'select',
      options: ['sm', 'md', 'lg'],
    },
  },
};

export default meta;

type Story = StoryObj<typeof Button>;

export const Primary: Story = {};

export const Secondary: Story = {
  args: { intent: 'secondary' },
};

export const Danger: Story = {
  args: { intent: 'danger' },
};

export const Ghost: Story = {
  args: { intent: 'ghost' },
};

export const Disabled: Story = {
  args: { disabled: true },
};
