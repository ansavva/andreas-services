import { AlertDialog as BaseAlertDialog } from '@base-ui/react/alert-dialog';

import { Dialog } from '../dialog/Dialog';

// AlertDialog shares its Backdrop/Viewport/Popup/Title/Description/Close/Portal
// components with Dialog (Base UI re-exports the same underlying parts) — only
// Root/Trigger/Handle differ, so we reuse the styled Dialog parts directly.
export const AlertDialog = {
  Root: BaseAlertDialog.Root,
  Trigger: BaseAlertDialog.Trigger,
  Portal: Dialog.Portal,
  Backdrop: Dialog.Backdrop,
  Viewport: Dialog.Viewport,
  Popup: Dialog.Popup,
  Title: Dialog.Title,
  Description: Dialog.Description,
  Close: Dialog.Close,
  Handle: BaseAlertDialog.Handle,
  createHandle: BaseAlertDialog.createHandle,
};
