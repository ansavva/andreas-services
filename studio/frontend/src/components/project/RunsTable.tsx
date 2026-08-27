import { useCallback, useEffect, useState } from "react";

import {
  Alert,
  Badge,
  Button,
  DateInput,
  Field,
  Input,
  Select,
  Spinner,
  Text,
  type DateStatus,
} from "@ansavva/design-system";

import { getRuns } from "../../apis/studio";
import { formatDate } from "../../utils/format";
import type { RunStatus, RunSummary } from "../../types";
import { MediaThumb } from "../media/MediaThumb";

interface Props {
  projectId: string;
  /** The project's characters, so the filter offers names rather than ids. */
  characters: Array<{ id: string; slug: string; display_name: string }>;
  onOpen: (run: RunSummary) => void;
}

const STATUSES: RunStatus[] = ["pending", "running", "succeeded", "failed", "cancelled"];

const STATUS_INTENT: Record<RunStatus, "neutral" | "success" | "danger" | "warning"> = {
  pending: "neutral",
  running: "warning",
  succeeded: "success",
  failed: "danger",
  cancelled: "neutral",
};

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
        ...(status ? { status } : {}),
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
      <div className="flex flex-wrap items-end gap-2 rounded-md border border-line bg-card p-3">
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
                ...characters.map((each) => ({ value: each.id, label: each.display_name })),
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

        <Button size="sm" onClick={() => fetchPage(null)}>
          Apply
        </Button>
      </div>

      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not load runs</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      {!loading && runs.length === 0 && !error && (
        <Text variant="body" tone="muted">
          No runs match that.
        </Text>
      )}

      <div className="flex flex-col gap-2">
        {runs.map((run) => (
          <button
            key={run.id}
            type="button"
            onClick={() => onOpen(run)}
            className="flex w-full items-center gap-3 rounded-md border border-line bg-card p-2 text-left
                       transition-colors hover:bg-surface-alt
                       focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            {/* The thumbnail is the run's first output, signed by the listing —
                which is what the projection on the listing row is for. A run that
                has not produced anything yet shows its kind instead. */}
            <span className="size-14 shrink-0 overflow-hidden rounded-md border border-line bg-surface-alt">
              {run.thumb ? (
                <MediaThumb
                  nodeId={run.thumb.node}
                  url={run.thumb.url}
                  name=""
                  aspect="auto"
                />
              ) : (
                <span className="flex h-full w-full items-center justify-center text-xs text-muted">
                  {run.kind}
                </span>
              )}
            </span>

            <span className="min-w-0 flex-1">
              {/* A run has no label. The date is what identifies one to a
                  person, which is what the old slug was imitating by carrying a
                  timestamp; the model is the next most useful thing about it. */}
              <Text variant="body" className="truncate">
                {formatDate(run.created)}
              </Text>
              <Text variant="caption" tone="muted" className="truncate">
                {run.model}
              </Text>
              {/* Lineage is what makes a chain readable at a glance: this run was
                  built off another's output, and that is usually the reason it
                  exists. */}
              {run.lineage?.from_run && (
                <Text variant="caption" tone="muted" className="truncate">
                  chained from a previous run
                </Text>
              )}
            </span>

            <Badge intent={STATUS_INTENT[run.status]}>{run.status}</Badge>

            {/* Recorded when the provider reports it and never computed —
                Replicate's prediction metrics differ by model, and a number this
                app worked out itself would be a guess wearing a currency sign. */}
            <Text variant="caption" tone="muted" className="w-20 shrink-0 text-right tabular-nums">
              {run.cost ? `${run.cost.currency} ${run.cost.amount.toFixed(3)}` : "—"}
            </Text>
          </button>
        ))}
      </div>

      {loading && (
        <div className="flex justify-center py-6">
          <Spinner size="md" label="Loading runs" />
        </div>
      )}

      {cursor !== null && !loading && (
        <div className="flex justify-center">
          <Button intent="ghost" size="sm" onClick={() => fetchPage(cursor)}>
            Load more
          </Button>
        </div>
      )}
    </div>
  );
}
