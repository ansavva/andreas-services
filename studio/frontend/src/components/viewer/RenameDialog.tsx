import { useCallback, useEffect, useRef, useState } from "react";

import { Button, Dialog, Field, Input, Text, iconButtonClass } from "@ansavva/design-system";

import { PencilIcon } from "../common/icons";

interface Props {
  /** The current name, which is what the field opens pre-filled with. */
  name: string;
  /** Runs on submit. Rejecting keeps the dialog open with the message shown. */
  onRename: (next: string) => Promise<unknown>;
  /**
   * Where the dialog paints — the player's own container while it can go
   * fullscreen, and nothing anywhere else.
   *
   * **This is the whole reason this component exists.** Rename used to be an
   * inline field wedged into the viewer's chrome strip, because the Fullscreen
   * API paints only the fullscreen element's descendants and a dialog portalled
   * to `<body>` is mounted, focused, keyboard-reachable and invisible while a
   * frame is filling the screen. `Dialog.Root`'s `container` (design system
   * 0.16.0) aims the portal at the element that *is* fullscreen, so the dialog
   * is simply the right control again.
   *
   * An ELEMENT, not a ref: the parts read it while rendering. `MediaPlayer`
   * reports its container from the ref callback for exactly this.
   */
  container?: HTMLElement | null;
  size?: "sm" | "md";
  /** Extra classes for the trigger. */
  className?: string;
}

/**
 * Rename one file, in a dialog that paints inside fullscreen.
 *
 * The field opens holding the old name with the **stem** selected: renaming
 * `wave-porch.jpeg` almost never means renaming the `.jpeg`, and a select-all
 * makes losing the extension the default outcome of typing.
 *
 * A rejected rename keeps the dialog open with the reason underneath. That is
 * the whole reason the API distinguishes 409 from 400 — "that name is taken" is
 * something you fix by typing a different name, and closing to say so would
 * throw away what you had typed.
 *
 * The browse rows keep `RenameForm` instead, and that is not an inconsistency
 * left behind: a row can give the field a full line of its own, which is both
 * cheaper and better than a dialog for a list you are working down. What the
 * row form was never good at is the case this replaces — a fixed-height chrome
 * strip over a photograph, where the same flex child rendered about forty
 * pixels wide.
 */
export function RenameDialog({ name, onRename, container, size = "md", className }: Props) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const field = useRef<HTMLInputElement>(null);

  // Stepping to another file must not leave the previous one's name sitting in
  // an open field — the same reset the old pencil-in-place performed.
  useEffect(() => {
    setOpen(false);
    setValue(name);
    setError(null);
  }, [name]);

  useEffect(() => {
    if (!open) return;
    const input = field.current;
    if (!input) return;
    input.focus();
    const dot = name.lastIndexOf(".");
    input.setSelectionRange(0, dot > 0 ? dot : name.length);
  }, [name, open]);

  const submit = useCallback(() => {
    const next = value.trim();
    if (!next || next === name) {
      setOpen(false);
      return;
    }

    setBusy(true);
    setError(null);
    onRename(next)
      .then(() => setOpen(false))
      .catch((failure: Error) => setError(failure.message))
      .finally(() => setBusy(false));
  }, [name, onRename, value]);

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next: boolean) => {
        setOpen(next);
        if (!next) {
          setValue(name);
          setError(null);
        }
      }}
      container={container ?? null}
    >
      {/* The trigger renders its own <button>, so it wears the icon button's
          classes rather than holding an `IconButton` — a button in a button is
          invalid HTML browsers resolve by dropping one of them. */}
      <Dialog.Trigger
        aria-label={`Rename ${name}`}
        title={`Rename ${name}`}
        className={iconButtonClass({ size, className })}
      >
        <PencilIcon className={size === "sm" ? "size-4 fill-none stroke-current stroke-[1.5]" : undefined} />
      </Dialog.Trigger>

      <Dialog.Backdrop />
      <Dialog.Popup className="flex w-full max-w-md flex-col gap-4 p-4">
        <Dialog.Title>Rename</Dialog.Title>

        {/* A form, so Enter submits without a keydown handler of its own — and
            so the page's single-key shortcuts leave it alone, which
            `useKeyboardNav` arranges by ignoring events targeting an INPUT. */}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
          className="flex flex-col gap-3"
        >
          <Field.Root name="name">
            <Field.Label>Name</Field.Label>
            <Input
              ref={field}
              value={value}
              onValueChange={setValue}
              placeholder={name}
              aria-label="Name"
            />
          </Field.Root>

          {error && (
            <Text variant="caption" className="text-danger">
              {error}
            </Text>
          )}

          <div className="flex flex-wrap justify-end gap-2">
            <Dialog.Close>Cancel</Dialog.Close>
            <Button type="submit" size="sm" disabled={busy}>
              {busy ? "Saving…" : "Save name"}
            </Button>
          </div>
        </form>
      </Dialog.Popup>
    </Dialog.Root>
  );
}
