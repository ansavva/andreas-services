import { useCallback, useEffect, useRef, useState } from "react";

import { Input, Text } from "@ansavva/design-system";
import { CheckIcon, CloseIcon } from "./icons";

export type RenameTone = "row" | "chrome";

interface Props {
  /** The current name, which is what the field opens pre-filled with. */
  name: string;
  /** Runs on submit. Rejecting keeps the field open with the message shown. */
  onRename: (next: string) => Promise<unknown>;
  /** Called once the rename lands, and on cancel. The parent owns "is it open". */
  onClose: () => void;
  tone?: RenameTone;
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
 * Inline rather than in a dialog, for the same reason delete has no dialog: this
 * is also rendered inside the viewer chrome, which is often inside a fullscreen
 * element, and anything portalled to `<body>` is simply not painted while one
 * is. Editing where the name already sits is the better interaction anyway — the
 * old name is the starting point for the new one, so the field opens holding it
 * with the *stem* selected, and typing replaces the name without eating the
 * extension.
 *
 * A rejected rename keeps the field open with the reason underneath it. That is
 * the whole reason the API distinguishes 409 from 400: "that name is taken" is
 * something you fix by typing a different name, and closing the field to say so
 * would throw away what you had typed.
 */
export function RenameForm({ name, onRename, onClose, tone = "row", className = "" }: Props) {
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
      // rename from also closing the reel this is sitting inside.
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
        <IconButton type="submit" tone={tone} disabled={busy} label="Save name">
          <CheckIcon />
        </IconButton>
        <IconButton type="button" tone={tone} onClick={onClose} label="Cancel rename (Esc)">
          <CloseIcon />
        </IconButton>
      </div>

      {error && (
        <Text variant="caption" className={tone === "chrome" ? "text-white" : "text-danger"}>
          {error}
        </Text>
      )}
    </form>
  );
}

function IconButton({
  children,
  label,
  tone,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string; tone: RenameTone }) {
  return (
    <button
      {...props}
      aria-label={label}
      title={label}
      className={`shrink-0 rounded-md transition-colors disabled:opacity-60 ${toneStyles[tone]}
                  focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary`}
    >
      {children}
    </button>
  );
}

export const toneStyles: Record<RenameTone, string> = {
  row: "p-2 text-muted hover:bg-surface-alt hover:text-ink",
  chrome: "p-2 text-white/80 hover:bg-white/15 hover:text-white",
};
