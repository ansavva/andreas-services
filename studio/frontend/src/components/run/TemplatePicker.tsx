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
  /** True while this run has no cast — a template would have nothing to fill from. */
  disabled?: boolean;
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
 * ## What it does NOT copy
 *
 * The template's `description` and `tags` describe the image it makes, not the
 * run that makes it, so they belong to a promotion rather than to a plan. They
 * stay on the template until somebody promotes an output into a character.
 */
export function TemplatePicker({ onPick, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const load = useCallback(() => getTemplates(), []);
  const library = useResource(open ? ["templates"] : null, open ? load : null);

  return (
    <>
      <Button
        size="sm"
        intent="secondary"
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
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
              {(library.data?.templates ?? []).map((entry) => (
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
                </button>
              ))}
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
