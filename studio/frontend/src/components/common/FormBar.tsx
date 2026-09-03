import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { Alert, Button, Text } from "@ansavva/design-system";

interface Props {
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  onRevert: () => void;
  /** A caption for the left edge — `revision 5`. Set in mono: it is metadata. */
  meta?: ReactNode;
  /** The last save's refusal. Rendered above the row, under one title. */
  error?: string | null;
  /**
   * Pin the row to the bottom of a small screen.
   *
   * For a form longer than a phone, where a Save you scroll back to is a Save
   * people stop pressing. Never at the top: the app header already holds
   * `top-0`, and a second sticky row slid under it.
   */
  sticky?: boolean;
}

/** How long a successful save reads as "Saved" before the label settles. */
const SAVED_FOR_MS = 2000;

/**
 * "Saved", briefly.
 *
 * A row that says `Saved` forever says nothing — it was the pristine label on
 * two forms and the disabled label on three others. Two seconds is long enough
 * to be read and short enough that the row returns to its resting state.
 * Exported for the one field that saves on its own: tags in the file drawer.
 */
export function useSavedFlash(): [boolean, () => void] {
  const [on, setOn] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  const flash = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    setOn(true);
    timer.current = setTimeout(() => setOn(false), SAVED_FOR_MS);
  }, []);
  return [on, flash];
}

/**
 * The one save row.
 *
 * Five forms had five of these — a sticky bar at the top, an inline pair with
 * the revision trailing, a pair with it leading, Save/Cancel, Save/Revert/Close
 * — and four ways of saying the form was dirty. This is the one shape: caption
 * left, Revert then Save right, both dead until something changed.
 *
 * **The enabled state is the dirty indication.** No badge, no label swap to
 * `Saved` while pristine, no dot beside the button. What a person needs to know
 * is whether pressing does anything, and a disabled button says exactly that.
 * The only other word the row speaks is `Saved`, for two seconds after a save
 * that stuck — inferred from `saving` falling while the form is clean, so no
 * caller has to report success separately from clearing its busy flag.
 *
 * **Revert, never Cancel or Discard.** Revert puts the last saved values back
 * in place; Cancel is for closing an edit session or a drawer, and this row
 * closes nothing.
 */
export function FormBar({ dirty, saving, onSave, onRevert, meta, error, sticky }: Props) {
  const [saved, flash] = useSavedFlash();
  const wasSaving = useRef(false);
  useEffect(() => {
    if (wasSaving.current && !saving && !dirty && !error) flash();
    wasSaving.current = saving;
  }, [dirty, error, flash, saving]);

  const label = saving ? "Saving…" : saved && !dirty ? "Saved" : "Save";

  return (
    // Painted only while it can have content scrolling under it. Inside a
    // drawer or a card the page colour would read as a band.
    <div
      data-form-bar
      className={`flex flex-col gap-2 border-t border-line pt-2 ${
        sticky
          ? "sticky bottom-0 z-10 bg-bg pb-[calc(0.5rem+env(safe-area-inset-bottom))] lg:static lg:bg-transparent lg:pb-0"
          : ""
      }`}
    >
      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not save</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}
      <div className="flex items-center gap-2">
        {meta ? (
          <Text variant="caption" tone="muted" family="mono" className="min-w-0 truncate tabular-nums">
            {meta}
          </Text>
        ) : null}
        <div className="flex-1" />
        <Button intent="secondary" size="sm" disabled={!dirty || saving} onClick={onRevert}>
          Revert
        </Button>
        <Button size="sm" disabled={!dirty || saving} onClick={onSave}>
          {label}
        </Button>
      </div>
    </div>
  );
}
