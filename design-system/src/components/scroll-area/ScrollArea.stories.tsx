import type { Meta, StoryObj } from '@storybook/react';

import { ScrollArea } from './ScrollArea';

const meta: Meta<typeof ScrollArea.Root> = {
  title: 'Components/ScrollArea',
  component: ScrollArea.Root,
};

export default meta;

type Story = StoryObj<typeof ScrollArea.Root>;

export const Default: Story = {
  render: (args) => (
    <ScrollArea.Root {...args} className="h-48 w-64 rounded-md border border-line">
      <ScrollArea.Viewport>
        <ScrollArea.Content className="p-4 text-sm text-ink">
          {Array.from({ length: 20 }, (_, i) => (
            <p key={i} className="py-1">
              Row {i + 1}
            </p>
          ))}
        </ScrollArea.Content>
      </ScrollArea.Viewport>
      <ScrollArea.Scrollbar>
        <ScrollArea.Thumb />
      </ScrollArea.Scrollbar>
    </ScrollArea.Root>
  ),
};
