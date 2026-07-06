import type { Meta, StoryObj } from '@storybook/react';

import { Tabs } from './Tabs';

const meta: Meta<typeof Tabs.Root> = {
  title: 'Components/Tabs',
  component: Tabs.Root,
};

export default meta;

type Story = StoryObj<typeof Tabs.Root>;

export const Default: Story = {
  render: (args) => (
    <Tabs.Root {...args} defaultValue="overview" className="w-96">
      <Tabs.List>
        <Tabs.Tab value="overview">Overview</Tabs.Tab>
        <Tabs.Tab value="activity">Activity</Tabs.Tab>
        <Tabs.Tab value="settings">Settings</Tabs.Tab>
        <Tabs.Indicator />
      </Tabs.List>
      <Tabs.Panel value="overview">Project overview and key metrics.</Tabs.Panel>
      <Tabs.Panel value="activity">Recent activity across the team.</Tabs.Panel>
      <Tabs.Panel value="settings">Project settings and preferences.</Tabs.Panel>
    </Tabs.Root>
  ),
};
