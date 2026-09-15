import { buttonClass } from "@ansavva/design-system";

/**
 * The Cancel in a dialog's footer, as a button.
 *
 * `Dialog.Close` and `AlertDialog.Close` ship as a TEXT slot — `self-start
 * py-xs text-sm font-medium`, no box — so beside a `Button` they read as a
 * stray label pinned to the top of the row. Every footer here is "Cancel,
 * then the action", so the Cancel takes the secondary button's box and
 * `self-auto` to sit on the same line as its neighbour. Sized to match the
 * action next to it, which is `md` everywhere but the destroy dialog.
 */
export function cancelClass(size: "sm" | "md" = "md"): string {
  return buttonClass({ intent: "secondary", size, className: "self-auto" });
}
