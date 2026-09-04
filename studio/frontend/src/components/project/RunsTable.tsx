import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Button, DateInput, Field, Input, Select, type DateStatus } from "@ansavva/design-system";

import { EmptyState } from "../common/EmptyState";
import { FilterBar } from "../common/FilterBar";
import { LoadError } from "../common/LoadError";
import { SectionLoading } from "../common/SectionLoading";
import { getRuns } from "../../apis/studio";
import { useSearchParamState } from "../../hooks/useSearchParamState";
import type { RunStatus, RunSummary } from "../../types";
import { RunList } from "../run/RunList";

interface Props {
  projectId: string;
  /** The project's characters, so the filter offers names rather than ids. */
  characters: Array<{ id: string; name: string }>;
  /** A run's address — the rows are links. */
  to: (run: RunSummary) => string;
}

/**
 * What the filter offers, and `draft` is on it deliberately.
 *
 * **"Any status" includes drafts, and this table asks for them explicitly.** The
 * route hides them from a listing that names no status, on the reasoning that a
 * grid mixing intentions with submissions is a grid nobody can read. That is a
 * fair default for a route; it is not one a control labelled `Any status` may
 * apply silently. Drafts are the one thing a person has to be able to FIND — an
 * unsent payload nobody can see is a queue nobody works through — and the
 * `draft` badge is what keeps the grid readable once they are in it.
 *
 * `discarded` is absent: it is gone, and offering a filter for it would suggest
 * otherwise.
 */
const STATUSES: RunStatus[] = [
  "draft",
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
 * **The five fields are URL state now, behind `FilterBar`, collapsed by
 * default.** They used to fill an always-open panel above the list — three
 * runs in a fresh project paid for a search interface with nothing to search.
 * The panel is chrome; the values underneath are the address's, exactly as the
 * file browser's `q`/`tags` are, so a filtered view of a project's runs
 * survives a reload and is a link somebody can be handed.
 *
 * `cursor` is real pagination rather than an offset: the rows are ranged on the
 * creation timestamp under the project's partition, so a page is a query.
 */
export function RunsTable({ projectId, characters, to }: Props) {
  const [status, setStatus] = useSearchParamState("status", "");
  const [character, setCharacter] = useSearchParamState("character", "");
  const [model, setModel] = useSearchParamState("model", "");
  const [since, setSince] = useSearchParamState("since", "");

  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /**
   * One fetch, either replacing the list or appending to it.
   *
   * The filters are *not* debounced and the model box applies on Enter rather
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
        // nothing but unsent payloads drew an empty grid and read `runs 0`,
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

  // The filters that are *chosen* rather than typed re-query on change; the
  // model box is applied on Enter. `model` is in the callback's dependencies
  // but not this effect's, deliberately.
  useEffect(() => {
    fetchPage(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, status, character, since]);

  const activeFilterCount = [status, character, model.trim(), since].filter(Boolean).length;

  /**
   * One write, not four.
   *
   * `useSearchParamState` gives each field its own setter, and each reads the
   * URL fresh from its own render — calling all four in one handler has every
   * one of them build its `next` from the SAME snapshot, so only the last
   * dispatch's single deletion survives. Clearing every field at once needs
   * one `URLSearchParams` with all four keys gone, written in one navigation.
   */
  const [searchParams, setSearchParams] = useSearchParams();
  const clearFilters = useCallback(() => {
    const next = new URLSearchParams(searchParams);
    next.delete("status");
    next.delete("character");
    next.delete("model");
    next.delete("since");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <FilterBar activeCount={activeFilterCount} onClear={clearFilters} label="Filter runs">
          <div className="min-w-40">
            <Field.Root name="status">
              <Field.Label>Status</Field.Label>
              <Select
                options={[
                  { value: "", label: "Any status" },
                  ...STATUSES.map((each) => ({ value: each, label: each })),
                ]}
                value={status}
                onValueChange={setStatus}
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
                value={character}
                onValueChange={setCharacter}
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
        </FilterBar>
      </div>

      {/* One slot, not two: a spinner appearing where the list would sit and an
          empty state appearing where the filter panel's edge sits used to read
          as two different screens depending on which fired, most noticeably
          while editing a filter — the message's position jumped. */}
      {error ? (
        <LoadError what="runs" message={error} onRetry={() => fetchPage(null)} />
      ) : loading && runs.length === 0 ? (
        <SectionLoading label="Loading runs" />
      ) : runs.length === 0 ? (
        <EmptyState title="Nothing here matches that search." />
      ) : (
        <>
          <RunList runs={runs} to={(run) => to(run as RunSummary)} />

          {loading && <SectionLoading label="Loading more runs" />}

          {cursor !== null && !loading && (
            <div className="flex justify-center">
              <Button intent="secondary" size="sm" onClick={() => fetchPage(cursor)}>
                Load more
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
