import type { Meta, StoryObj } from '@storybook/react';

import { Avatar } from './Avatar';

const meta: Meta<typeof Avatar.Root> = {
  title: 'Components/Avatar',
  component: Avatar.Root,
};

export default meta;

type Story = StoryObj<typeof Avatar.Root>;

export const WithFallback: Story = {
  render: (args) => (
    <Avatar.Root {...args}>
      <Avatar.Fallback>JD</Avatar.Fallback>
    </Avatar.Root>
  ),
};

export const WithImage: Story = {
  render: (args) => (
    <Avatar.Root {...args}>
      <Avatar.Image src="https://i.pravatar.cc/80" alt="Jane Doe" />
      <Avatar.Fallback>JD</Avatar.Fallback>
    </Avatar.Root>
  ),
};
