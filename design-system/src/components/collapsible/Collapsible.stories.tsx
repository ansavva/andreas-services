import type { Meta, StoryObj } from '@storybook/react';

import { Collapsible } from './Collapsible';

const meta: Meta<typeof Collapsible.Root> = {
  title: 'Components/Collapsible',
  component: Collapsible.Root,
};

export default meta;

type Story = StoryObj<typeof Collapsible.Root>;

export const Default: Story = {
  render: (args) => (
    <Collapsible.Root {...args} className="w-72" defaultOpen>
      <Collapsible.Trigger>Show changelog</Collapsible.Trigger>
      <Collapsible.Panel>
        <p className="pt-2">v1.2.0 — Added dark mode support.</p>
      </Collapsible.Panel>
    </Collapsible.Root>
  ),
};
