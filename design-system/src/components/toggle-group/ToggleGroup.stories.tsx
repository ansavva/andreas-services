import type { Meta, StoryObj } from '@storybook/react';

import { Toggle } from '../toggle/Toggle';

import { ToggleGroup } from './ToggleGroup';

const meta: Meta<typeof ToggleGroup> = {
  title: 'Components/ToggleGroup',
  component: ToggleGroup,
};

export default meta;

type Story = StoryObj<typeof ToggleGroup>;

export const Default: Story = {
  render: (args) => (
    <ToggleGroup {...args} defaultValue={['bold']} aria-label="Text formatting">
      <Toggle value="bold" aria-label="Bold">
        B
      </Toggle>
      <Toggle value="italic" aria-label="Italic">
        I
      </Toggle>
      <Toggle value="underline" aria-label="Underline">
        U
      </Toggle>
    </ToggleGroup>
  ),
};
