import type { RunFeedRow, RunRecord } from "../../types";

/**
 * A feed row built from the record, for a run the feed has not loaded — or
 * for one it holds stale.
 *
 * A cold link lands here before any listing has answered, and the record
 * carries everything the row does except the cast's names — those are looked
 * up in the project's own characters, and a character no longer in the
 * project reads as deleted, which is what the feed says too.
 *
 * **`GET /api/runs/<id>` and `?view=feed` answer the same run in two shapes**,
 * and this is the one place that reconciles them: the lightbox draws a cold
 * link from it, and `useRunWatch` patches a landed run into the feed's cached
 * pages with it rather than re-reading the page the run sits on.
 *
 * `characters` accepts a null name because the feed's own `cast` is the other
 * caller's source, and a deleted character is already null there.
 */
export function rowOfRecord(
  record: RunRecord,
  characters: Array<{ id: string; name: string | null }>,
): RunFeedRow {
  // The first output that can actually be DRAWN, which is what the API's own
  // `_feed_row` picks for `thumb` — `outputs[0]` was a second answer to the
  // same question, and it disagreed whenever that output's node was gone.
  const first = record.outputs.find((asset) => asset.url);
  return {
    id: record.id,
    lib: record.lib,
    project: record.project,
    status: record.status,
    kind: record.kind,
    engine: record.engine,
    model: record.model,
    created: record.created,
    updated: null,
    submitted: record.submitted,
    completed: record.completed,
    error: record.error,
    cost: record.cost,
    ...(record.fingerprint ? { fingerprint: record.fingerprint } : {}),
    plan: record.plan,
    characters: record.characters,
    cast: (record.cast ?? record.characters).map((id) => ({
      id,
      name: characters.find((each) => each.id === id)?.name ?? null,
    })),
    sends: record.sends,
    outputs: record.outputs,
    thumb: first?.url ? { node: first.node, url: first.url } : null,
  };
}
