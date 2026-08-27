import { useCallback, useEffect, useRef, useState } from "react";

import { buttonClass } from "@ansavva/design-system";
import { QuestionIcon, TrashIcon } from "./icons";

type Tone = "row" | "chrome" | "bar" | "page";
type Phase = "idle" | "armed" | "busy";

interface Props {
  /** What is about to be destroyed, e.g. "3 files". Used in the labels. */
  noun: string;
  /** Runs on the second press. Rejecting leaves the button disarmed. */
  onConfirm: () => Promise<unknown>;
  /** Which surface this sits on. See `toneStyles`. */
  tone?: Tone;
  disabled?: boolean;
  className?: string;
}

/**
 * Delete, confirmed twice, in one button and without a dialog.
 *
 * **The confirmation is the button changing under your finger**, not a modal:
 * press once and it turns red and says what it is about to destroy, press again
 * and it does it. That is a deliberate choice over the usual dialog, for two
 * reasons.
 *
 * The first is that a portalled dialog is not painted while a `<video>` is in
 * native fullscreen, which is exactly where deleting a clip is most natural —
 * the same constraint that keeps `CopyKeyButton`'s feedback inline.
 *
 * The second is that a modal trains the wrong reflex. A dialog that always
 * appears in the same place gets a second click aimed at it before it renders;
 * a button that *changes what it says where your finger already is* cannot be
 * dismissed without reading it. The arming is not a formality — it expires.
 *
 * Three things disarm it: the timeout, moving focus away, and Escape. So a
 * half-pressed delete left on screen is never still live when you come back to
 * it, and it never swallows an Escape meant for the overlay around it — the key
 * is only intercepted while this particular button is armed and focused.
 */
const ARMED_MS = 4000;

export function ConfirmDeleteButton({
  noun,
  onConfirm,
  tone = "row",
  disabled = false,
  className = "",
}: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Set on unmount so a resolving promise cannot call setState afterwards —
  // deleting from the reel closes the pane the button lives in.
  const gone = useRef(false);

  useEffect(() => {
    gone.current = false;
    return () => {
      gone.current = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const disarm = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setPhase((current) => (current === "armed" ? "idle" : current));
  }, []);

  const press = useCallback(() => {
    if (phase === "busy") return;

    if (phase === "idle") {
      setPhase("armed");
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        if (!gone.current) setPhase("idle");
      }, ARMED_MS);
      return;
    }

    if (timer.current) clearTimeout(timer.current);
    setPhase("busy");
    void onConfirm()
      .catch(() => {
        /* the caller surfaces the message; this only owns the button */
      })
      .finally(() => {
        if (!gone.current) setPhase("idle");
      });
  }, [onConfirm, phase]);

  const label =
    phase === "busy"
      ? `Deleting ${noun}…`
      : phase === "armed"
        ? `Confirm — delete ${noun}`
        : `Delete ${noun}`;

  /**
   * The `bar` tone is a trash can at rest and a sentence once armed.
   *
   * At rest it sits in a selection bar that already says "3 selected", so
   * spelling out "Delete 3 files" beside that was a third of the bar spent
   * restating its own count — and the trash can is the same one the rows use, so
   * there is nothing new to learn. Armed is the opposite case and gets the full
   * text: this is the press that destroys forty files at once, and an icon
   * changing colour is not enough to carry that. Growing is deliberate too — the
   * button expands leftward under a cursor already resting on the can, so the
   * second click lands on the armed control rather than somewhere it used to be.
   */
  const showsText = (tone === "bar" && phase !== "idle") || tone === "page";

  return (
    <button
      type="button"
      onClick={press}
      onBlur={disarm}
      onKeyDown={(event) => {
        // Only while armed, so the reel's own Escape handler is untouched the
        // rest of the time.
        if (event.key === "Escape" && phase === "armed") {
          event.stopPropagation();
          disarm();
        }
      }}
      disabled={disabled || phase === "busy"}
      aria-label={label}
      title={label}
      // The package has no `danger` intent — `button.props.ts` records that the
      // token set has no `danger-text` to pair with a danger fill — so the armed
      // state is the package's own class recipe with the fill swapped, the same
      // move `humbugg/app` makes for its three destructive actions. Hand-rolling
      // the button instead would be the first component of a second design
      // system.
      //
      // The swap is an inline style, not a `bg-danger` class, and that is not
      // fussiness: two Tailwind utilities setting the same property are resolved
      // by their order in the generated stylesheet, not by the order they appear
      // in this attribute, so layering one over `buttonClass`'s own fill is a
      // coin toss. An inline style always wins. It reads the semantic role
      // rather than a literal, which is the rule that actually matters.
      style={
        phase === "armed" && showsText
          ? {
              backgroundColor: "var(--color-danger)",
              color: "var(--color-bg)",
              // `buttonClass` is `whitespace-nowrap` at a fixed `h-8`, which is
              // right for a word and wrong for a sentence. The armed label is
              // the consequence spelled out, and on a phone a long noun ran off
              // the side and took the page's horizontal scroll with it. Inline
              // for the same reason the fill is: two utilities setting one
              // property are resolved by stylesheet order, not by the order
              // they are written here.
              height: "auto",
              minHeight: "2rem",
              whiteSpace: "normal",
              textAlign: "start",
              paddingBlock: "0.25rem",
            }
          : undefined
      }
      className={`${
        showsText
          ? buttonClass({ intent: "secondary", size: "sm" })
          : `shrink-0 rounded-md transition-colors ${
              phase === "armed" ? armedStyles[tone] : toneStyles[tone]
            }`
      } disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2
         focus-visible:outline-primary ${className}`}
    >
      {/* The armed state has to reach a screen reader as a statement, not as a
          colour change on an icon. */}
      <span className="sr-only" aria-live="assertive">
        {phase === "armed" ? `Press again to delete ${noun}` : ""}
      </span>

      {/* **This said `Confirm — delete …` in every phase**, including at rest,
          which made a page-level destroy render as though it were already armed
          the moment the page loaded. It also put the visible text at odds with
          `aria-label`, which was reading the correct `label` all along. The
          arming is the whole mechanism — "a button that changes what it says
          where your finger already is" — and it cannot change into what it
          already said. */}
      {showsText ? (
        <span aria-hidden="true">
          {phase === "busy"
            ? "Deleting…"
            : phase === "armed"
              ? `Confirm — delete ${noun}`
              : "Delete"}
        </span>
      ) : phase === "armed" ? (
        // A question mark while armed: the icon itself has to say that this
        // press is not the same as the last one.
        <QuestionIcon />
      ) : (
        <TrashIcon />
      )}
    </button>
  );
}

/**
 * Matches `CopyKeyButton`'s tones — these two sit next to each other, and a
 * delete that read as a different *kind* of control would be a second thing to
 * learn rather than the sibling it is.
 *
 * The armed variants are complete replacements rather than additions for the
 * same reason the bar's fill is inline: `text-muted` and `text-danger` are the
 * same property, and which of two conflicting utilities wins is decided by the
 * stylesheet, not by this file.
 */
const toneStyles: Record<Tone, string> = {
  row: "p-2 text-muted hover:bg-surface-alt hover:text-danger",
  chrome: "p-2 text-white/80 hover:bg-white/15 hover:text-white",
  // Text at rest AND armed, unlike `bar` — but not the *same* text. This is a
  // page-level destroy — a project with its runs, a character with its
  // references — and a trash can in a page header reads as "delete something on
  // this page" rather than "delete this page's subject". So at rest it is the
  // bare word, which also keeps it a small control beside a title on a phone;
  // armed, the `noun` carries the weight and it says exactly what is about to
  // go.
  page: "",
  // Idle only — the armed and busy states of this tone render as text, not as an
  // icon, so `armedStyles.bar` is never reached. It matches `row` because it is
  // literally the same trash can on a different surface.
  bar: "p-2 text-muted hover:bg-surface-alt hover:text-danger",
};

const armedStyles: Record<Tone, string> = {
  row: "p-2 bg-danger/15 text-danger",
  chrome: "p-2 bg-danger/80 text-white",
  // Never reached: `page` always renders as text, so it takes the same inline
  // danger fill `bar` does when armed.
  page: "",
  bar: "p-2 bg-danger/15 text-danger",
};
