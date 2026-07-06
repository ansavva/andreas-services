import type { Meta, StoryObj } from '@storybook/react';

import { Combobox } from './Combobox';

const meta: Meta<typeof Combobox.Root> = {
  title: 'Components/Combobox',
  component: Combobox.Root,
};

export default meta;

type Story = StoryObj<typeof Combobox.Root>;

const fruits = ['Apple', 'Banana', 'Cherry', 'Date', 'Elderberry'];

export const Default: Story = {
  render: (args) => (
    <Combobox.Root {...args} items={fruits}>
      <Combobox.Label>Fruit</Combobox.Label>
      <Combobox.InputGroup className="w-64">
        <Combobox.Input placeholder="Search fruit..." />
        <Combobox.Icon />
      </Combobox.InputGroup>
      <Combobox.Portal>
        <Combobox.Positioner sideOffset={4}>
          <Combobox.Popup>
            <Combobox.Empty>No fruit found.</Combobox.Empty>
            <Combobox.List>
              {(fruit: string) => (
                <Combobox.Item key={fruit} value={fruit}>
                  {fruit}
                  <Combobox.ItemIndicator />
                </Combobox.Item>
              )}
            </Combobox.List>
          </Combobox.Popup>
        </Combobox.Positioner>
      </Combobox.Portal>
    </Combobox.Root>
  ),
};
