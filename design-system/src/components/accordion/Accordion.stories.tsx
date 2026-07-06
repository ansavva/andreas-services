import type { Meta, StoryObj } from '@storybook/react';

import { Accordion } from './Accordion';

const meta: Meta<typeof Accordion.Root> = {
  title: 'Components/Accordion',
  component: Accordion.Root,
};

export default meta;

type Story = StoryObj<typeof Accordion.Root>;

const items = [
  { value: 'shipping', title: 'Shipping', body: 'Free shipping on orders over $50.' },
  { value: 'returns', title: 'Returns', body: 'Returns accepted within 30 days.' },
];

export const Default: Story = {
  render: (args) => (
    <Accordion.Root {...args} className="w-96" defaultValue={['shipping']}>
      {items.map((item) => (
        <Accordion.Item key={item.value} value={item.value}>
          <Accordion.Header>
            <Accordion.Trigger>{item.title}</Accordion.Trigger>
          </Accordion.Header>
          <Accordion.Panel>{item.body}</Accordion.Panel>
        </Accordion.Item>
      ))}
    </Accordion.Root>
  ),
};
