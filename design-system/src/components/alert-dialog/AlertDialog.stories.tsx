import type { Meta, StoryObj } from '@storybook/react';

import { Button } from '../button/Button';

import { AlertDialog } from './AlertDialog';

const meta: Meta<typeof AlertDialog.Root> = {
  title: 'Components/AlertDialog',
  component: AlertDialog.Root,
};

export default meta;

type Story = StoryObj<typeof AlertDialog.Root>;

export const Default: Story = {
  render: (args) => (
    <AlertDialog.Root {...args}>
      <AlertDialog.Trigger render={<Button intent="danger">Delete account</Button>} />
      <AlertDialog.Portal>
        <AlertDialog.Backdrop />
        <AlertDialog.Viewport>
          <AlertDialog.Popup>
            <AlertDialog.Title>Delete account</AlertDialog.Title>
            <AlertDialog.Description>
              This action cannot be undone. This will permanently delete your account.
            </AlertDialog.Description>
            <div className="mt-4 flex justify-end gap-2">
              <AlertDialog.Close render={<Button intent="ghost">Cancel</Button>} />
              <AlertDialog.Close render={<Button intent="danger">Delete</Button>} />
            </div>
          </AlertDialog.Popup>
        </AlertDialog.Viewport>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  ),
};
