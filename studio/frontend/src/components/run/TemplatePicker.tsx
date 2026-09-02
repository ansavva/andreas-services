import { useCallback, useState } from "react";

import { Alert, Button, Dialog, Text } from "@ansavva/design-system";

import { getTemplates } from "../../apis/studio";
import { ApertureSpinner } from "../common/Aperture";
import { useResource } from "../../hooks/useResource";
import { LoadError } from "../common/LoadError";

interface Props {
  /**
   * Called with the chosen template's prompt. The caller puts it in the box; it
   * does NOT save, because picking a template is the start of an edit rather
   * than the end of one.
   */
  onPick: (prompt: string) => void;
  /** How many characters this run binds. `{character.1.…}` is the first of them. */
  cast: number;
}

/**
 * The highest `{character.N.…}` a template cites, or 0 if it cites none.
 *
 * **Not every template needs a character**, which is why this is a number rather
 * than a flag: one built entirely from `{block.…}` fills against a run that
 * binds nobody, and a picker that hid every template until a cast existed would
 * hide exactly the ones that never needed one.
 */
export function castNeededBy(prompt: string): number {
  let most = 0;
  for (const [, digits] of prompt.matchAll(/\{character\.(\d+)\./g)) {
    most = Math.max(most, Number(digits));
  }
  return most;
}

/**
 * Start a prompt from a template somebody wrote.
 *
 * **This is what the turnaround was, minus the fan-out.** A reference angle was
 * a prompt plus a description plus tags, and the only thing that could use one
 * rendered all fourteen at once, each chained off the first. The prompts are
 * the part worth keeping: a template is picked for one run, filled from that
 * run's cast, and edited before it goes anywhere.
 *
 * ## It fills the box and stops
 *
 * Choosing does not save and does not submit. The prompt lands in the editor as
 * text a person then reads, changes and approves — which is where hard rule #2
 * has always put the decision. A picker that saved would make "look at a
 * template" and "commit to it" the same gesture.
 *
 * ## Nothing here is blocked
 *
 * A template built from `{block.…}` alone fills against a run that binds
 * nobody, so gating the list on a cast would hide exactly the templates that
 * never needed one. And gating the ROWS is barely better: a person who wants a
 * template that cites a character they have not added yet wants to add the
 * character, not to be told they may not look. So every row is pickable, a row
 * that needs more cast than the run has says so, and the editor names the
 * citation that did not expand and offers the fix beside it.
 *
 * ## What it does NOT copy
 *
 * The template's `description` and `tags` describe the image it makes, not the
 * run that makes it, so they belong to a promotion rather than to a plan. They
 * stay on the template until somebody promotes an output into a character.
 */
export function TemplatePicker({ onPick, cast }: Props) {
  const [open, setOpen] = useState(false);
  const load = useCallback(() => getTemplates(), []);
  const library = useResource(open ? ["templates"] : null, open ? load : null);

  return (
    <>
      <Button size="sm" intent="secondary" onClick={() => setOpen(true)}>
        Start from a template
      </Button>

      {open && (
        <Dialog.Root open onOpenChange={(next: boolean) => !next && setOpen(false)}>
          <Dialog.Backdrop />
          <Dialog.Popup className="flex max-h-[85vh] w-full max-w-xl flex-col gap-3 p-4">
            <Dialog.Title>Start from a template</Dialog.Title>

            {library.loading && (
              <div className="flex h-32 items-center justify-center">
                <ApertureSpinner size="md" label="Loading templates" />
              </div>
            )}

            {library.error && <LoadError what="templates" message={library.error} onRetry={library.reload} />}

            {library.data && library.data.templates.length === 0 && (
              <Alert.Root>
                <Alert.Title>This library holds no templates</Alert.Title>
                <Alert.Description>
                  Push some with <code>studio templates push --path &lt;file&gt;</code>,
                  or write one on the Templates page.
                </Alert.Description>
              </Alert.Root>
            )}

            <div className="flex flex-col gap-2 overflow-auto">
              {(library.data?.templates ?? []).map((entry) => {
                const needs = castNeededBy(entry.prompt);
                const short = needs > cast;
                return (
                  <button
                    key={entry.id}
                    type="button"
                    onClick={() => {
                      onPick(entry.prompt);
                      setOpen(false);
                    }}
                    className="flex flex-col gap-1 rounded border border-line p-3 text-left
                               transition-colors hover:bg-surface-alt
                               focus-visible:outline-2 focus-visible:-outline-offset-2
                               focus-visible:outline-primary"
                  >
                    <Text variant="body">{entry.name || entry.id}</Text>
                    {/* The first line only. A template is a wall of prose and a
                        list of walls is unreadable; what a person is choosing
                        between is which template, not which paragraph. */}
                    <Text variant="caption" tone="muted">
                      {entry.prompt.trim().split("\n")[0]}
                    </Text>
                    {/* **Said, not enforced.** Every template is pickable: it
                        lands in the box, the preview names the citation that
                        will not expand, and the cast is editable right there.
                        Blocking the pick instead would be this screen deciding
                        which of its own problems a person is allowed to see. */}
                    {short && (
                      <Text variant="caption" tone="muted">
                        Cites character {needs}; this run binds{" "}
                        {cast === 0 ? "none" : cast} — add one after picking.
                      </Text>
                    )}
                  </button>
                );
              })}
            </div>

            <div className="flex justify-end">
              <Button size="sm" intent="secondary" onClick={() => setOpen(false)}>
                Cancel
              </Button>
            </div>
          </Dialog.Popup>
        </Dialog.Root>
      )}
    </>
  );
}
