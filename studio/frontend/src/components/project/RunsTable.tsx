import { useCallback, useEffect, useState } from "react";

import {
  Button,
  DateInput,
  Field,
  Input,
  Select,
  type DateStatus,
} from "@ansavva/design-system";

import { EmptyState } from "../common/EmptyState";
import { LoadError } from "../common/LoadError";
import { SectionLoading } from "../common/SectionLoading";
import { getRuns } from "../../apis/studio";
import type { RunStatus, RunSummary } from "../../types";
import { RunList } from "../run/RunList";

interface Props {
  projectId: string;
  /** The project's characters, so the filter offers names rather than ids. */
  characters: Array<{ id: string; name: string }>;
  onOpen: (run: RunSummary) => void;
}

/**
 * What the filter offers, and `draft` is on it deliberately.
 *
 * **"Any status" includes drafts, and this table asks for them explicitly.** The
 * route hides them from a listing that names no status, on the reasoning that a
 * grid mixing intentions with submissions is a grid nobody can read. That is a
 * fair default for a route; it is not one a control labelled `Any status` may
 * apply silently. Drafts are the one thing a person has to be able to FIND — an
 * unapproved payload nobody can see is a queue nobody works through — and the
 * `draft` badge is what keeps the grid readable once they are in it.
 *
 * `discarded` is absent: it is gone, and offering a filter for it would suggest
 * otherwise.
 */
const STATUSES: RunStatus[] = [
  "draft",
  "approved",
  "pending",
  "running",
  "succeeded",
  "failed",
  "cancelled",
];

/**
 * Every run in a project, filterable — the screen studio did not have.
 *
 * It could not have had one. A run was a timestamp-named folder holding three
 * JSON documents the app was forbidden to parse, so "runs on this model that
 * failed last week" meant listing every project, listing every run folder,
 * reading `request.json` in each and grepping — which is what `runs find` did,
 * and why it took as long as it did.
 *
 * **Every filter here is a field on a row, so combining them costs one query.**
 * The listing rows carry the model, the status, the thumbnail and the cost as a
 * small projection — a deliberate exception to this table's no-projections rule,
 * and a safe one, because a run is immutable once it completes and there is
 * nothing to keep in step. Without it this grid would be a batch read over
 * hundreds of envelopes.
 *
 * `cursor` is real pagination rather than an offset: the rows are ranged on the
 * creation timestamp under the project's partition, so a page is a query.
 */
export function RunsTable({ projectId, characters, onOpen }: Props) {
  const [status, setStatus] = useState<string | null>(null);
  const [model, setModel] = useState("");
  const [character, setCharacter] = useState<string | null>(null);
  const [since, setSince] = useState("");

  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /**
   * One fetch, either replacing the list or appending to it.
   *
   * The filters are *not* debounced and the model box submits on Enter rather
   * than per keystroke: a request per character typed into `google/nano-banana-pro`
   * is twenty-one queries for one answer, and the last of them can land before
   * an earlier one.
   */
  const fetchPage = useCallback(
    (next: string | null) => {
      setLoading(true);
      setError(null);
      getRuns({
        project: projectId,
        // "Any status" means any. The route hides drafts from a listing that
        // names no status, so a filter reading `Any status` was returning
        // everything EXCEPT the runs waiting to be looked at — a project holding
        // nothing but unapproved payloads drew an empty grid and read `runs 0`,
        // which is indistinguishable from nothing having been planned. Asking
        // for a specific status still narrows to exactly it.
        ...(status ? { status } : { include: "drafts" }),
        ...(model.trim() ? { model: model.trim() } : {}),
        ...(character ? { character } : {}),
        ...(since ? { since } : {}),
        ...(next ? { cursor: next } : {}),
      })
        .then((page) => {
          setRuns((current) => (next === null ? page.runs : [...current, ...page.runs]));
          setCursor(page.cursor);
        })
        .catch((err: Error) => setError(err.message))
        .finally(() => setLoading(false));
    },
    [character, model, projectId, since, status],
  );

  // The filters that are *chosen* rather than typed re-query on change; the model
  // box is applied by the button beside it. `model` is in the callback's
  // dependencies but not this effect's, deliberately.
  useEffect(() => {
    fetchPage(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, status, character, since]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-2 rounded-none border border-line bg-card p-3">
        <div className="min-w-40">
          <Field.Root name="status">
            <Field.Label>Status</Field.Label>
            <Select
              options={[
                { value: "", label: "Any status" },
                ...STATUSES.map((each) => ({ value: each, label: each })),
              ]}
              value={status ?? ""}
              onValueChange={(next: string) => setStatus(next === "" ? null : next)}
            />
          </Field.Root>
        </div>

        <div className="min-w-48">
          <Field.Root name="character">
            <Field.Label>Character</Field.Label>
            <Select
              options={[
                { value: "", label: "Any character" },
                ...characters.map((each) => ({ value: each.id, label: each.name })),
              ]}
              value={character ?? ""}
              onValueChange={(next: string) => setCharacter(next === "" ? null : next)}
            />
          </Field.Root>
        </div>

        <div className="min-w-56 flex-1">
          <Field.Root name="model">
            <Field.Label>Model</Field.Label>
            <Input
              value={model}
              placeholder="google/nano-banana-pro"
              onValueChange={setModel}
              onKeyDown={(event: React.KeyboardEvent) => {
                if (event.key === "Enter") fetchPage(null);
              }}
            />
          </Field.Root>
        </div>

        <div className="min-w-40">
          <Field.Root name="since">
            <Field.Label>Since</Field.Label>
            {/* `DateInput`, not `<input type="date">` — the package has no such
                type and says why: the browser control formats to the browser's
                locale and cannot be styled consistently.

                The status argument is not detail. `""` means both "cleared" and
                "half-typed", and re-querying on a half-typed date would drop the
                filter under the cursor on every keystroke, so only `valid` and
                `empty` are acted on. */}
            <DateInput
              value={since}
              picker="calendar"
              onValueChange={(next: string, status: DateStatus) => {
                if (status === "valid" || status === "empty") setSince(next);
              }}
            />
          </Field.Root>
        </div>

        {/* `md`, so it stands at the same 44px as the Selects beside it — see
            the note in `NewRunStrip` on the package's three control heights. */}
        <Button onClick={() => fetchPage(null)}>
          Search
        </Button>
      </div>

      {error && <LoadError what="runs" message={error} onRetry={() => fetchPage(null)} />}

      {!loading && runs.length === 0 && !error && (
        <EmptyState title="Nothing here matches that search." />
      )}

      <RunList runs={runs} onOpen={(run) => onOpen(run as RunSummary)} />

      {loading && <SectionLoading label="Loading runs" />}

      {cursor !== null && !loading && (
        <div className="flex justify-center">
          <Button intent="secondary" size="sm" onClick={() => fetchPage(cursor)}>
            Load more
          </Button>
        </div>
      )}
    </div>
  );
}
