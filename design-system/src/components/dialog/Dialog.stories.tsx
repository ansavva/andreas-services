import type { Meta, StoryObj } from '@storybook/react';

import { Button } from '../button/Button';

import { Dialog } from './Dialog';

const meta: Meta<typeof Dialog.Root> = {
  title: 'Components/Dialog',
  component: Dialog.Root,
};

export default meta;

type Story = StoryObj<typeof Dialog.Root>;

export const Default: Story = {
  render: (args) => (
    <Dialog.Root {...args}>
      <Dialog.Trigger render={<Button>Edit profile</Button>} />
      <Dialog.Portal>
        <Dialog.Backdrop />
        <Dialog.Viewport>
          <Dialog.Popup>
            <Dialog.Title>Edit profile</Dialog.Title>
            <Dialog.Description>Update your account details below.</Dialog.Description>
            <div className="mt-4 flex justify-end gap-2">
              <Dialog.Close render={<Button intent="ghost">Cancel</Button>} />
              <Dialog.Close render={<Button>Save</Button>} />
            </div>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  ),
};
