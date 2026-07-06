import type { Meta, StoryObj } from '@storybook/react';

import { Toolbar } from './Toolbar';

const meta: Meta<typeof Toolbar.Root> = {
  title: 'Components/Toolbar',
  component: Toolbar.Root,
};

export default meta;

type Story = StoryObj<typeof Toolbar.Root>;

export const Default: Story = {
  render: (args) => (
    <Toolbar.Root {...args} aria-label="Text formatting">
      <Toolbar.Group>
        <Toolbar.Button aria-label="Bold">B</Toolbar.Button>
        <Toolbar.Button aria-label="Italic">I</Toolbar.Button>
      </Toolbar.Group>
      <Toolbar.Separator />
      <Toolbar.Link href="#help">Help</Toolbar.Link>
    </Toolbar.Root>
  ),
};
