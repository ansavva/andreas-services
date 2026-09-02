import { useCallback, useState } from "react";

import { Alert, Button, Text } from "@ansavva/design-system";

import { getProject, getRun, setRunCharacters } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import type { RunRecord } from "../../types";

interface Props {
  runId: string;
  projectId: string;
  /** The run's cast, in the order `{character.1.…}` counts them. */
  value: string[];
  /** The run as the API reports it after the write, never a local merge. */
  onSaved: (run: RunRecord) => void;
}

/**
 * Who a run is about — editable, which it was not.
 *
 * **A run's cast could only be set when it was created, and the app never set
 * it.** `POST /api/runs` takes `characters` and the new-run strip did not send
 * them, so every run made in the app bound nobody; nothing could then cite one,
 * because a prompt names its cast by POSITION and `{character.1.top}` had
 * nothing to fill from. The template picker was permanently unusable and the
 * reason was invisible.
 *
 * ## Order is the payload
 *
 * `{character.1.…}` is the first of these and `[Image1]` counts the same way, so
 * the chips show their position and clicking appends rather than inserting.
 * That is the same reason a run's sends are an ordered list rather than a set.
 *
 * ## Offered from the PROJECT's cast
 *
 * A run is about somebody the project is about; anything else is a character
 * that would not appear in the project's own listings afterwards. A project
 * with no characters shows the empty state rather than an empty control.
 */
export function RunCast({ runId, projectId, value, onSaved }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => getProject(projectId), [projectId]);
  const project = useResource(["project", projectId], load);
  const offered = project.data?.characters ?? [];

  const toggle = useCallback(
    async (id: string) => {
      const at = value.indexOf(id);
      const next = at >= 0 ? value.filter((each) => each !== id) : [...value, id];
      setBusy(true);
      setError(null);
      try {
        await setRunCharacters(runId, next);
        // **Re-read rather than merge.** `cast` is DERIVED — the record's own
        // `characters` when it has any, and otherwise whoever owns the images
        // the run binds — so a client that patched `characters` into the record
        // it already held would leave `cast` at whatever it was and the prompt
        // preview would keep refusing a citation that now resolves.
        onSaved(await getRun(runId));
      } catch (problem) {
        setError(problem instanceof Error ? problem.message : String(problem));
      } finally {
        setBusy(false);
      }
    },
    [onSaved, runId, value],
  );

  if (project.loading) return null;

  return (
    <div className="flex flex-col gap-2">
      <Text variant="caption" tone="muted">Characters</Text>
      <Text variant="caption" tone="muted">
        Who this run is about. A prompt cites them by position —{" "}
        <code>{"{character.1.top}"}</code> is the first.
      </Text>

      {offered.length === 0 ? (
        <Text variant="caption" tone="muted">
          This project has no characters. Add one on the project&rsquo;s Overview
          tab, then it can be picked here.
        </Text>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {offered.map((each) => {
            const at = value.indexOf(each.id);
            return (
              <Button
                key={each.id}
                size="sm"
                disabled={busy}
                intent={at >= 0 ? "primary" : "secondary"}
                onClick={() => void toggle(each.id)}
              >
                {at >= 0 ? `${at + 1}. ` : ""}
                {each.display_name || each.slug}
              </Button>
            );
          })}
        </div>
      )}

      {error && (
        <Alert.Root intent="danger">
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}
    </div>
  );
}
