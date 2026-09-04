import { useCallback, useEffect, useRef, useState } from "react";

import { IconButton, Input, Text } from "@ansavva/design-system";
import { CheckIcon, CloseIcon } from "./icons";

interface Props {
  /** The current name, which is what the field opens pre-filled with. */
  name: string;
  /** Runs on submit. Rejecting keeps the field open with the message shown. */
  onRename: (next: string) => Promise<unknown>;
  /** Called once the rename lands, and on cancel. The parent owns "is it open". */
  onClose: () => void;
  className?: string;
}

/**
 * The open half of a rename: a text field where the name already is.
 *
 * **The parent owns whether this is open, and that is what makes the field
 * usable.** It used to live inside `RenameButton`, which put it in the row's
 * control strip — a flex child sharing a line with the opening button, the copy
 * button and the delete button, so it rendered about forty pixels wide and you
 * renamed a file through a letterbox. A parent that knows a rename is in
 * progress can give the field a line of its own, and the rows do.
 *
 * **It used to be inline because of fullscreen, and now it is inline because a
 * row is the right place for it.** The second copy of this control lived in the
 * viewer's chrome, which was often inside a fullscreen element where anything
 * portalled to `<body>` is not painted — so a dialog was impossible there and
 * every rename was this field. `Drawer.Root`'s `container` (design system
 * 0.16.0) removed the impossibility, and the object screen's rename is one
 * field in `viewer/FileDetailsPanel` now — it was briefly a dialog of its own,
 * which is the step that got merged away. What is left here is the case that was
 * always better inline: a listing you are working down, where the row can give
 * the field a full line and the old name is the starting point for the new one.
 * The field opens holding it with the *stem* selected, so typing replaces the
 * name without eating the extension.
 *
 * A rejected rename keeps the field open with the reason underneath it. That is
 * the whole reason the API distinguishes 409 from 400: "that name is taken" is
 * something you fix by typing a different name, and closing the field to say so
 * would throw away what you had typed.
 */
export function RenameForm({ name, onRename, onClose, className = "" }: Props) {
  const [value, setValue] = useState(name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The wrapper is what carries the ref, and the input is found inside it. The
  // design system's `Input` is used elsewhere in this repo with `value`,
  // `onValueChange`, `type` and `placeholder` and nothing else, so reaching for
  // it through the DOM keeps this component off props the package may not
  // forward — and if it ever stops rendering a bare <input>, the effect below
  // finds nothing and does nothing rather than breaking the rename.
  const fieldRef = useRef<HTMLDivElement>(null);

  // Select the stem, not the whole value: renaming `wave-porch.jpeg` almost
  // never means renaming the `.jpeg`, and a select-all makes losing the
  // extension the default outcome of typing.
  useEffect(() => {
    const input = fieldRef.current?.querySelector("input");
    if (!input) return;
    input.focus();
    const dot = name.lastIndexOf(".");
    input.setSelectionRange(0, dot > 0 ? dot : name.length);
  }, [name]);

  const submit = useCallback(() => {
    const next = value.trim();
    if (!next || next === name) {
      onClose();
      return;
    }

    setBusy(true);
    setError(null);
    onRename(next)
      .then(() => onClose())
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  }, [name, onClose, onRename, value]);

  return (
    // A form, so Enter submits without a keydown handler of its own — and so the
    // reel's global arrow-key navigation leaves it alone, which `useKeyboardNav`
    // arranges by ignoring events whose target is an INPUT.
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      // Escape is handled here rather than on the field: the event bubbles out of
      // the input either way, and stopping it at the form keeps a cancelled
      // rename from also closing the page this is sitting inside.
      onKeyDown={(event) => {
        if (event.key !== "Escape") return;
        event.stopPropagation();
        onClose();
      }}
      aria-label={`Rename ${name}`}
      className={`flex min-w-0 flex-col gap-1 ${className}`}
    >
      <div ref={fieldRef} className="flex min-w-0 items-center gap-1">
        <Input value={value} onValueChange={setValue} placeholder={name} />
        {/* The PACKAGE's IconButton. There was a local re-implementation right
            here until design-system 0.17.0, and the three things it existed to
            hand-write are all the component's own now: `aria-label` (a required
            prop), `title` mirrored from it, and a 44px hit area on a coarse
            pointer. The last was the reason for the copy — it needed studio's
            `.touch-target` class, and the package's `sm` carries the target
            itself now, as a centred pseudo-element that grows the target
            without growing the drawn box. */}
        <IconButton type="submit" size="sm" disabled={busy} label="Save name">
          <CheckIcon />
        </IconButton>
        <IconButton type="button" size="sm" onClick={onClose} label="Cancel rename (Esc)">
          <CloseIcon />
        </IconButton>
      </div>

      {error && (
        <Text variant="caption" className="text-danger">
          {error}
        </Text>
      )}
    </form>
  );
}
