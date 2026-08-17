import { useCallback, useEffect, useRef, useState } from "react";

import { Input, Text } from "@ansavva/design-system";

type Tone = "row" | "chrome";

interface Props {
  /** The current name, which is what the field opens pre-filled with. */
  name: string;
  /** Runs on submit. Rejecting keeps the field open with the message shown. */
  onRename: (next: string) => Promise<unknown>;
  tone?: Tone;
  className?: string;
}

/**
 * Rename in place: a pencil that becomes a text field where the name already is.
 *
 * Inline rather than in a dialog, for the same reason delete has no dialog —
 * this chrome is often inside a fullscreen element, where anything portalled to
 * `<body>` is simply not painted. Editing where the name already sits is also
 * the better interaction: the old name is the starting point for the new one,
 * so the field opens holding it with the *stem* selected, and typing replaces
 * the name without eating the extension.
 *
 * A rejected rename keeps the field open with the reason underneath it. That is
 * the whole reason the API distinguishes 409 from 400: "that name is taken" is
 * something you fix by typing a different name, and closing the field to say so
 * would throw away what you had typed.
 */
export function RenameButton({ name, onRename, tone = "row", className = "" }: Props) {
  const [open, setOpen] = useState(false);
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

  // Reopening on a different file must not offer the previous one's name.
  useEffect(() => {
    setValue(name);
    setOpen(false);
    setError(null);
  }, [name]);

  const start = useCallback(() => {
    setValue(name);
    setError(null);
    setOpen(true);
  }, [name]);

  // Select the stem, not the whole value: renaming `wave-porch.jpeg` almost
  // never means renaming the `.jpeg`, and a select-all makes losing the
  // extension the default outcome of typing.
  useEffect(() => {
    if (!open) return;
    const input = fieldRef.current?.querySelector("input");
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
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  }, [name, onRename, value]);

  if (!open) {
    return (
      <button
        type="button"
        onClick={start}
        aria-label={`Rename ${name}`}
        title={`Rename ${name}`}
        className={`shrink-0 rounded-md transition-colors ${toneStyles[tone]}
                    focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary
                    ${className}`}
      >
        <svg
          viewBox="0 0 24 24"
          aria-hidden="true"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="size-5 fill-none stroke-current stroke-[1.5]"
        >
          <path d="M4 20h4l10-10a2.83 2.83 0 1 0-4-4L4 16Z" />
          <path d="M13.5 6.5 17.5 10.5" />
        </svg>
      </button>
    );
  }

  return (
    // A form, so Enter submits without a keydown handler of its own — and so
    // the reel's global arrow-key navigation leaves it alone, which
    // `useKeyboardNav` arranges by ignoring events whose target is an INPUT.
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      // Escape is handled here rather than on the field: the event bubbles out
      // of the input either way, and stopping it at the form keeps a cancelled
      // rename from also closing the reel this is sitting inside.
      onKeyDown={(event) => {
        if (event.key !== "Escape") return;
        event.stopPropagation();
        setOpen(false);
      }}
      aria-label={`Rename ${name}`}
      className="flex min-w-0 flex-1 flex-col gap-1"
    >
      <div ref={fieldRef} className="flex min-w-0 items-center gap-1">
        <Input value={value} onValueChange={setValue} placeholder={name} />
        <button
          type="submit"
          disabled={busy}
          aria-label="Save name"
          title="Save name"
          className={`shrink-0 rounded-md transition-colors disabled:opacity-60 ${toneStyles[tone]}
                      focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary`}
        >
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="size-5 fill-none stroke-current stroke-[1.5]"
          >
            <path d="m5 12.5 5 5L19 7" />
          </svg>
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Cancel rename"
          title="Cancel rename (Esc)"
          className={`shrink-0 rounded-md transition-colors ${toneStyles[tone]}
                      focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary`}
        >
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="size-5 fill-none stroke-current stroke-[1.5]"
          >
            <path d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      </div>

      {error && (
        <Text variant="caption" className={tone === "chrome" ? "text-white" : "text-danger"}>
          {error}
        </Text>
      )}
    </form>
  );
}

const toneStyles: Record<Tone, string> = {
  row: "p-2 text-muted hover:bg-surface-alt hover:text-ink",
  chrome: "p-2 text-white/80 hover:bg-white/15 hover:text-white",
};
