import type { Meta, StoryObj } from '@storybook/react';

import { Button } from '../button/Button';

import { Toast, useToastManager } from './Toast';

const meta: Meta<typeof Toast.Provider> = {
  title: 'Components/Toast',
  component: Toast.Provider,
};

export default meta;

type Story = StoryObj<typeof Toast.Provider>;

function ToastDemo() {
  const toastManager = useToastManager();

  return (
    <Button
      onClick={() =>
        toastManager.add({
          title: 'Changes saved',
          description: 'Your profile has been updated.',
        })
      }
    >
      Show toast
    </Button>
  );
}

export const Default: Story = {
  render: () => (
    <Toast.Provider>
      <ToastDemo />
      <Toast.Portal>
        <Toast.Viewport>
          <ToastList />
        </Toast.Viewport>
      </Toast.Portal>
    </Toast.Provider>
  ),
};

function ToastList() {
  const { toasts } = useToastManager();

  return (
    <>
      {toasts.map((toast) => (
        <Toast.Root key={toast.id} toast={toast}>
          <Toast.Title />
          <Toast.Description />
          <Toast.Close aria-label="Dismiss">×</Toast.Close>
        </Toast.Root>
      ))}
    </>
  );
}
