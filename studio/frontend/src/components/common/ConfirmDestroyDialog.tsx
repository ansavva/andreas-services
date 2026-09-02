import { useState } from "react";

import { AlertDialog, Button, Field, Input, Text, buttonClass } from "@ansavva/design-system";

interface Props {
  /** The button's label — also the dialog's action. "Delete", "Delete 54 files". */
  label: string;
  /** What is about to be destroyed, as a sentence. */
  title: string;
  /** What goes with it. The cascade, spelled out. */
  summary: string;
  /**
   * What has to be typed before the action is live.
   *
   * A name for an entity, a count for a selection — something the person has to
   * *read the dialog* to know. "yes" would be muscle memory.
   */
  confirmWord: string;
  onConfirm: () => Promise<unknown>;
  className?: string;
}

/**
 * The gate for a delete that takes other things with it.
 *
 * **`ConfirmDeleteButton` is still right for one file and wrong for this.** It
 * arms in place and the armed label is the whole confirmation, which is a good
 * bargain when the cost of being wrong is one frame you can see on screen. It
 * is a bad one when the press destroys twenty-nine runs, three scenes and a
 * movie — the label said so, but a second press in the same spot is exactly the
 * gesture a mis-click produces.
 *
 * So the cascade cases type the name. It is the standard shape for this and it
 * earns its friction honestly: the word cannot be guessed from muscle memory,
 * and getting it requires reading the sentence that says what is about to go.
 *
 * **This is not a replacement for the armed button**, and the reason changed
 * under it. It used to be that a portalled dialog is not painted while a
 * `<video>` is in native fullscreen, so the viewer could not have had one; the
 * design system's `container` prop (0.16.0) settles that, and both `Dialog` and
 * `AlertDialog` will paint inside a fullscreen element if handed it. What is
 * left is the argument about cost: one file is an armed button, a cascade is a
 * typed word.
 */
export function ConfirmDestroyDialog({
  label,
  title,
  summary,
  confirmWord,
  onConfirm,
  className,
}: Props) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const armed = typed.trim() === confirmWord;

  async function run() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      setOpen(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AlertDialog.Root
      open={open}
      onOpenChange={(next: boolean) => {
        setOpen(next);
        if (!next) {
          setTyped("");
          setError(null);
        }
      }}
    >
      {/* The trigger IS the button — `AlertDialog.Trigger` renders its own, so
          a `Button` inside it would be a button in a button.

          **There is no `danger` intent** — the package ships `primary`,
          `secondary` and `ghost`, and everything destructive in this app is a
          `bg-danger` override on top. `cn` is tailwind-merge, so the colour
          written here beats the intent's own. */}
      <AlertDialog.Trigger
        className={buttonClass({
          size: "sm",
          className: `bg-danger text-primary-text hover:bg-danger-hover ${className ?? ""}`,
        })}
      >
        {label}
      </AlertDialog.Trigger>
      <AlertDialog.Backdrop />
      <AlertDialog.Popup className="flex w-full max-w-md flex-col gap-4 p-4">
        <AlertDialog.Title>{title}</AlertDialog.Title>
        <AlertDialog.Description>{summary}</AlertDialog.Description>

        <Field.Root name="confirm">
          <Field.Label>
            Type <code>{confirmWord}</code> to confirm
          </Field.Label>
          <Input value={typed} onValueChange={setTyped} autoFocus aria-label="Confirm" />
        </Field.Root>

        {error && (
          <Text variant="caption" className="text-danger">
            {error}
          </Text>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          <AlertDialog.Close>Cancel</AlertDialog.Close>
          <Button
            size="sm"
            disabled={!armed || busy}
            className="bg-danger text-primary-text hover:bg-danger-hover"
            onClick={() => void run()}
          >
            {busy ? "Deleting…" : label}
          </Button>
        </div>
      </AlertDialog.Popup>
    </AlertDialog.Root>
  );
}
