import type { Meta, StoryObj } from '@storybook/react';

import { Select } from './Select';

const meta: Meta<typeof Select.Root> = {
  title: 'Components/Select',
  component: Select.Root,
};

export default meta;

type Story = StoryObj<typeof Select.Root>;

const fruits = ['Apple', 'Banana', 'Cherry', 'Date', 'Elderberry'];

export const Default: Story = {
  render: (args) => (
    <Select.Root {...args} defaultValue="Banana">
      <Select.Trigger aria-label="Fruit" className="w-48">
        <Select.Value />
        <Select.Icon />
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner>
          <Select.Popup>
            <Select.List>
              {fruits.map((fruit) => (
                <Select.Item key={fruit} value={fruit}>
                  <Select.ItemText>{fruit}</Select.ItemText>
                  <Select.ItemIndicator />
                </Select.Item>
              ))}
            </Select.List>
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  ),
};
