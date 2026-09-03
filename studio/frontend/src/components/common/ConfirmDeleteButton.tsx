import { Button, IconButton } from "@ansavva/design-system";

import { useArmed } from "../../hooks/useArmed";
import { dangerButtonClass } from "./danger";
import { QuestionIcon, TrashIcon } from "./icons";

type Tone = "text" | "icon";

interface Props {
  /** What is about to be destroyed, e.g. "3 files". Used in the labels. */
  noun: string;
  /** Runs on the second press. Rejecting leaves the button disarmed. */
  onConfirm: () => Promise<unknown>;
  /**
   * `text` is a labelled button — "Delete" at rest, the full sentence armed.
   * `icon` is a trash can that turns into a danger square with a question mark.
   * The accessible name is the same sentence either way.
   */
  tone?: Tone;
  disabled?: boolean;
  /** Extra classes for the resting face — a row over media passes its chrome fill. */
  className?: string;
}

/**
 * Delete, confirmed twice, in one button and without a dialog.
 *
 * **The confirmation is the button changing under your finger**, not a modal:
 * press once and it turns red and says what it is about to destroy, press again
 * and it does it. A dialog that always appears in the same place gets a second
 * click aimed at it before it renders; a button that *changes what it says
 * where your finger already is* cannot be dismissed without reading it. The
 * arming is not a formality — it expires. The mechanics are `useArmed`'s.
 *
 * **This is the gate for one thing** — a file, a folder, a run, a template, a
 * block nothing cites. Anything that takes other things with it goes through
 * `ConfirmDestroyDialog` and types the name; a bulk delete past `BULK_GATE`
 * types the count. The weight of the confirmation follows what is lost, never
 * which screen the control happens to sit on.
 *
 * **Two tones, down from four.** `row`, `bar`, `chrome` and `page` each had a
 * resting appearance of their own, which meant the same delete looked like a
 * different control on every surface. What actually varied was whether the
 * button had room for a word — so that is the whole axis now.
 */
export function ConfirmDeleteButton({
  noun,
  onConfirm,
  tone = "icon",
  disabled = false,
  className = "",
}: Props) {
  const { armed, busy, press, handlers } = useArmed({ onFire: onConfirm });

  const label = busy
    ? `Deleting ${noun}…`
    : armed
      ? `Confirm — delete ${noun}`
      : `Delete ${noun}`;

  // The armed state has to reach a screen reader as a statement, not as a
  // colour change on an icon.
  const announcement = (
    <span className="sr-only" aria-live="assertive">
      {armed ? `Press again to delete ${noun}` : ""}
    </span>
  );

  if (tone === "icon") {
    return (
      <IconButton
        label={label}
        size="sm"
        // The package's own danger row — the one fill it measured for a glyph.
        intent={armed || busy ? "danger" : "ghost"}
        onClick={press}
        {...handlers}
        disabled={disabled || busy}
        className={`shrink-0 ${armed || busy ? "" : "text-muted hover:text-danger"} ${className}`}
      >
        {announcement}
        {/* A question mark while armed: the icon itself has to say that this
            press is not the same as the last one. */}
        {armed ? <QuestionIcon /> : <TrashIcon />}
      </IconButton>
    );
  }

  return (
    <Button
      intent="secondary"
      size="sm"
      onClick={press}
      {...handlers}
      disabled={disabled || busy}
      aria-label={label}
      title={label}
      className={armed || busy ? dangerButtonClass({ wraps: true, className }) : className}
    >
      {announcement}
      {/* The bare word at rest, never the confirmation — the arming is the whole
          mechanism, and it cannot change into what it already said. */}
      <span aria-hidden="true">
        {busy ? "Deleting…" : armed ? `Confirm — delete ${noun}` : "Delete"}
      </span>
    </Button>
  );
}
