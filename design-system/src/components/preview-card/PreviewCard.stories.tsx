import type { Meta, StoryObj } from '@storybook/react';

import { PreviewCard } from './PreviewCard';

const meta: Meta<typeof PreviewCard.Root> = {
  title: 'Components/PreviewCard',
  component: PreviewCard.Root,
};

export default meta;

type Story = StoryObj<typeof PreviewCard.Root>;

export const Default: Story = {
  render: (args) => (
    <PreviewCard.Root {...args}>
      <PreviewCard.Trigger
        render={
          <a href="#andreas-services" className="text-accent underline">
            @andreas-services
          </a>
        }
      />
      <PreviewCard.Portal>
        <PreviewCard.Positioner sideOffset={8}>
          <PreviewCard.Popup>
            <p className="text-sm font-semibold text-ink">Andreas Services</p>
            <p className="mt-1 text-sm text-muted">
              AI consulting and content, evergreen and heritage.
            </p>
          </PreviewCard.Popup>
        </PreviewCard.Positioner>
      </PreviewCard.Portal>
    </PreviewCard.Root>
  ),
};
