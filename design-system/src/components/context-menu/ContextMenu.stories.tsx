import type { Meta, StoryObj } from '@storybook/react';

import { ContextMenu } from './ContextMenu';

const meta: Meta<typeof ContextMenu.Root> = {
  title: 'Components/ContextMenu',
  component: ContextMenu.Root,
};

export default meta;

type Story = StoryObj<typeof ContextMenu.Root>;

export const Default: Story = {
  render: (args) => (
    <ContextMenu.Root {...args}>
      <ContextMenu.Trigger className="flex h-32 w-64 items-center justify-center rounded-md border border-dashed border-line text-sm text-muted">
        Right-click here
      </ContextMenu.Trigger>
      <ContextMenu.Portal>
        <ContextMenu.Positioner>
          <ContextMenu.Popup>
            <ContextMenu.Item>Copy</ContextMenu.Item>
            <ContextMenu.Item>Paste</ContextMenu.Item>
          </ContextMenu.Popup>
        </ContextMenu.Positioner>
      </ContextMenu.Portal>
    </ContextMenu.Root>
  ),
};
