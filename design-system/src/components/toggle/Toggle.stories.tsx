import type { Meta, StoryObj } from '@storybook/react';

import { Toggle } from './Toggle';

const meta: Meta<typeof Toggle> = {
  title: 'Components/Toggle',
  component: Toggle,
  args: {
    children: 'Bold',
    'aria-label': 'Toggle bold',
  },
};

export default meta;

type Story = StoryObj<typeof Toggle>;

export const Default: Story = {};

export const Pressed: Story = {
  args: { defaultPressed: true },
};
