import { useState } from "react";

import { AlertDialog, Button, buttonClass, Field, Input, Text } from "@ansavva/design-system";


/**
 * Where an armed button stops being enough for a bulk delete.
 *
 * Under this many, the cost of being wrong is a handful of frames still on
 * screen and the two-press button is proportionate. At or above it, the count
 * has to be typed — a selection is invisible once it is gone, and "select all"
 * followed by "delete" is two presses from emptying a folder.
 */
export const BULK_GATE = 5;

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
  disabled?: boolean;
  className?: string;
  /**
   * Controlled, for a caller whose opening control is not a button this can
   * render — a row in a listbox, say. With `open` given no trigger is drawn;
   * the caller owns both the control and the state.
   */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

/**
 * The gate for a delete that takes other things with it.
 *
 * **`ConfirmDeleteButton` is right for one thing and wrong for this.** It arms
 * in place and the armed label is the whole confirmation, which is a good
 * bargain when the cost of being wrong is one frame you can see on screen. It
 * is a bad one when the press destroys twenty-nine runs, three scenes and a
 * movie — or rewrites forty-three files to take a word off them — because a
 * second press in the same spot is exactly the gesture a mis-click produces.
 *
 * So the cascade cases type the name. It is the standard shape for this and it
 * earns its friction honestly: the word cannot be guessed from muscle memory,
 * and getting it requires reading the sentence that says what is about to go.
 *
 * **The weight follows what is lost, not which screen asks.** An entity with
 * children — a character, a project, a scene, a movie, a tag — types its name.
 * A selection at or past `BULK_GATE` types its count. One file, one run, one
 * template is the armed button. A block is one or the other depending on
 * whether anything cites it.
 */
export function ConfirmDestroyDialog({
  label,
  title,
  summary,
  confirmWord,
  onConfirm,
  disabled = false,
  className,
  open,
  onOpenChange,
}: Props) {
  const [ownOpen, setOwnOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const controlled = open !== undefined;
  const isOpen = controlled ? open : ownOpen;

  function change(next: boolean) {
    if (!controlled) setOwnOpen(next);
    onOpenChange?.(next);
    if (!next) {
      setTyped("");
      setError(null);
    }
  }

  const armed = typed.trim() === confirmWord;

  async function run() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      change(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AlertDialog.Root open={isOpen} onOpenChange={change}>
      {/* The trigger IS the button — `AlertDialog.Trigger` renders its own, so
          a `Button` inside it would be a button in a button. */}
      {!controlled && (
        <AlertDialog.Trigger
          disabled={disabled}
          className={buttonClass({ intent: "danger", size: "sm", className })}
        >
          {label}
        </AlertDialog.Trigger>
      )}
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
            intent="danger"
            size="sm"
            disabled={!armed || busy}
            onClick={() => void run()}
          >
            {busy ? "Deleting…" : label}
          </Button>
        </div>
      </AlertDialog.Popup>
    </AlertDialog.Root>
  );
}
