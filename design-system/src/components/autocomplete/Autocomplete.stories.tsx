import type { Meta, StoryObj } from '@storybook/react';

import { Autocomplete } from './Autocomplete';

const meta: Meta<typeof Autocomplete.Root> = {
  title: 'Components/Autocomplete',
  component: Autocomplete.Root,
};

export default meta;

type Story = StoryObj<typeof Autocomplete.Root>;

const cities = ['Athens', 'Auckland', 'Austin', 'Amsterdam'];

export const Default: Story = {
  render: (args) => (
    <Autocomplete.Root {...args} items={cities}>
      <Autocomplete.InputGroup className="w-64">
        <Autocomplete.Input placeholder="Search cities..." />
        <Autocomplete.Icon />
      </Autocomplete.InputGroup>
      <Autocomplete.Portal>
        <Autocomplete.Positioner sideOffset={4}>
          <Autocomplete.Popup>
            <Autocomplete.Empty>No cities found.</Autocomplete.Empty>
            <Autocomplete.List>
              {(city: string) => <Autocomplete.Item key={city} value={city} />}
            </Autocomplete.List>
          </Autocomplete.Popup>
        </Autocomplete.Positioner>
      </Autocomplete.Portal>
    </Autocomplete.Root>
  ),
};
