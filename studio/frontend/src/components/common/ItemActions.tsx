import { useCallback, useState } from "react";

import { Dropdown } from "@ansavva/design-system";

import { copyLabel, useCopyToClipboard } from "../../hooks/useCopyToClipboard";

interface Props {
  /** What is being acted on, written into every label. */
  name: string;
  /** A file's or folder's name path — what "Copy" puts on the clipboard. Not an
   *  S3 key; see `CopyKeyButton`, which this hands it to. */
  copyValue: string;
  /** What `copyValue` names, which is all that differs between the two labels. */
  copyNoun?: "key" | "prefix";
  /** Opens the parent's rename field. The parent owns it so it can be full width. */
  onRename: () => void;
  /** Opens the parent's destination picker on a move. */
  onMove: () => void;
  /**
   * Opens it on a copy. Optional because folders cannot be copied — there is no
   * folder-copy endpoint — so a folder card passes only `onMove`.
   */
  onCopyTo?: () => void;
  onDelete: () => Promise<unknown>;
}

/**
 * Every per-item action, behind one button.
 *
 * Each row used to carry its controls as a strip of icons — rename, copy,
 * delete — and adding move would have made four, on every folder card and every
 * file row, permanently, next to a name that is usually a forty-character
 * timestamp. The strip was reading as more chrome than content. So the actions
 * collapse into one trigger, and what a row shows at rest is the thing it names.
 *
 * Two of the four items behave unusually, and both are deliberate:
 *
 * * **Copy keeps the menu open.** `Dropdown.Item` closes on activation unless the
 *   click is `preventDefault`ed, and copy is the one action here whose entire
 *   feedback is the label changing to "Copied" — closing the menu would take the
 *   confirmation with it. So it stays open and reports, exactly as
 *   `CopyKeyButton` does elsewhere.
 * * **Delete arms rather than fires.** The item turns red and restates what it is
 *   about to destroy, and the second press does it — the same interaction
 *   `ConfirmDeleteButton` argues for, kept here rather than delegated to that
 *   component because a `role="menu"` may only contain menu items, and it is a
 *   plain button. Closing the menu disarms, so a half-pressed delete is never
 *   left live behind a closed menu.
 *
 * A `Dropdown` is absolutely positioned inside its own relative wrapper rather
 * than portalled, which is why this is safe on rows the way a `Dialog` would not
 * be — and it is still only used on the browse page. The viewer chrome keeps its
 * inline controls, because that bar is often inside a fullscreen element.
 */
export function ItemActions({
  name,
  copyValue,
  copyNoun = "key",
  onRename,
  onMove,
  onCopyTo,
  onDelete,
}: Props) {
  const [open, setOpen] = useState(false);
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const { status, copy } = useCopyToClipboard();

  const change = useCallback((next: boolean) => {
    setOpen(next);
    // Closing disarms: an armed delete waiting behind a menu nobody can see is
    // exactly the state `ConfirmDeleteButton`'s timeout exists to prevent.
    if (!next) setArmed(false);
  }, []);

  const pressDelete = useCallback(() => {
    if (!armed) {
      setArmed(true);
      return;
    }
    setBusy(true);
    void onDelete()
      .catch(() => {
        /* the page surfaces the message; this only owns the menu */
      })
      .finally(() => {
        setBusy(false);
        setArmed(false);
        setOpen(false);
      });
  }, [armed, onDelete]);

  return (
    <Dropdown.Root open={open} onOpenChange={change}>
      <Dropdown.Trigger
        aria-label={`Actions for ${name}`}
        title={`Actions for ${name}`}
        className="shrink-0 rounded-md p-2 text-muted transition-colors hover:bg-surface-alt hover:text-ink"
      >
        <svg
          viewBox="0 0 24 24"
          aria-hidden="true"
          className="size-5 fill-current stroke-none"
        >
          <circle cx="5" cy="12" r="1.6" />
          <circle cx="12" cy="12" r="1.6" />
          <circle cx="19" cy="12" r="1.6" />
        </svg>
      </Dropdown.Trigger>

      {/* Right-aligned: the trigger sits at the end of a row, so a menu growing
          rightwards from it would hang off the edge of the page. */}
      <Dropdown.Content className="left-auto right-0">
        <Dropdown.Item onSelect={onRename}>Rename…</Dropdown.Item>
        <Dropdown.Item onSelect={onMove}>Move…</Dropdown.Item>
        {/* "Copy to…" rather than "Copy", because the item below it copies the
            key to the clipboard and the two must not read as the same thing. */}
        {onCopyTo && <Dropdown.Item onSelect={onCopyTo}>Copy to…</Dropdown.Item>}

        <Dropdown.Item
          onClick={(event: React.MouseEvent) => {
            event.preventDefault();
            void copy(copyValue);
          }}
        >
          {/* `aria-live` so a screen reader hears an outcome whose only other
              signal is the label changing under a pointer. */}
          <span aria-live="polite">{copyLabel(status, `Copy ${copyNoun}`)}</span>
        </Dropdown.Item>

        <Dropdown.Item
          disabled={busy}
          onClick={(event: React.MouseEvent) => {
            // Arming must not close the menu — the confirmation *is* the item.
            if (!armed) event.preventDefault();
            pressDelete();
          }}
          className={armed ? "text-danger" : ""}
        >
          <span aria-live="assertive">
            {busy ? "Deleting…" : armed ? `Confirm — delete ${name}` : "Delete"}
          </span>
        </Dropdown.Item>
      </Dropdown.Content>
    </Dropdown.Root>
  );
}
