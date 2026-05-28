import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "@/api";
import { Badge, Button, ErrorBanner, Spinner, SubTabs } from "@/components/ui";
import { formatDate, truncate } from "@/utils/formatters";
import type { ReviewGroup } from "@/types";

const REVIEWS = ["pending", "approved", "rejected"] as const;
const REVIEW_TABS = REVIEWS.map((r) => ({ key: r, label: r }));

// Row-scoped busy keys so the per-button spinner and the "disable siblings"
// check share the same prefix. Events use evt:<id>, sub-events sub:<id>.
const eventKey = (id: string) => `evt:${id}`;
const subKey = (id: string) => `sub:${id}`;

// Append a freshly-loaded page, skipping parents already on screen. A parent can
// re-emit across a page split (it's introduced by whichever of its rows the index
// returns first); the re-emitted group is identical, so first-seen wins.
function mergeGroups(prev: ReviewGroup[], next: ReviewGroup[]): ReviewGroup[] {
  const seen = new Set(prev.map((g) => g.event.event_id));
  return [...prev, ...next.filter((g) => !seen.has(g.event.event_id))];
}

export function ReviewSection() {
  const api = useApi();
  const [searchParams, setSearchParams] = useSearchParams();
  const reviewParam = searchParams.get("review");
  const review = (REVIEWS as readonly string[]).includes(reviewParam ?? "")
    ? (reviewParam as string)
    : "pending";
  const setReview = (r: string) =>
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("review", r);
        return next;
      },
      { replace: true }
    );

  const [groups, setGroups] = useState<ReviewGroup[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The single in-flight action on the screen ("rowKey:action"). Drives the
  // per-button spinner and disables the rest of the affected row.
  const [busy, setBusy] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [pendingDeleteSubId, setPendingDeleteSubId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listEvents(review);
      setGroups(data.groups);
      setCursor(data.next_cursor);
      setSelected(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [api, review]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const loadMore = async () => {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const data = await api.listEvents(review, cursor);
      setGroups((prev) => mergeGroups(prev, data.groups));
      setCursor(data.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load more");
    } finally {
      setLoadingMore(false);
    }
  };

  const isBusy = (key: string) => busy === key;
  const rowBusy = (rowKey: string) => busy?.startsWith(`${rowKey}:`) ?? false;

  // A group belongs in the current tab when its parent's own status matches or
  // any of its occurrences do. Used after an optimistic edit to drop a group that
  // no longer has anything to show in this tab.
  const groupVisible = (g: ReviewGroup) =>
    g.event.review_status === review ||
    g.subevents.some((s) => s.review_status === review);

  // Maps over groups, applies `fn` to the matching parent's group, then prunes
  // any group that's no longer visible in this tab.
  const updateGroup = (
    eventId: string,
    fn: (g: ReviewGroup) => ReviewGroup
  ) =>
    setGroups((prev) =>
      prev.map((g) => (g.event.event_id === eventId ? fn(g) : g)).filter(groupVisible)
    );

  // Runs an action with per-button spinner + row lock, then applies an exact
  // optimistic update to the affected group only. We don't re-read the queue:
  // the server-side effects that change what this view displays are reproduced
  // locally (review/publish/delete are self-contained; cancel cascades
  // `cancelled` to the occurrences, handled in cancelEvt). Errors surface on the
  // section-level banner; local state isn't mutated on failure.
  const runAction = async (
    actionKey: string,
    call: () => Promise<unknown>,
    applyOptimistic: () => void
  ) => {
    setBusy(actionKey);
    setError(null);
    try {
      await call();
      applyOptimistic();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(null);
    }
  };

  // ─── parent (event) row actions ──────────────────────────────────────────
  const reviewEvt = (id: string, status: string) =>
    runAction(
      `${eventKey(id)}:review`,
      () => api.reviewEvent(id, status),
      () =>
        updateGroup(id, (g) => ({
          ...g,
          event: { ...g.event, review_status: status },
          parent_matches: status === review,
        }))
    );

  const publishEvt = (id: string, nextPublished: boolean) =>
    runAction(
      `${eventKey(id)}:publish`,
      () => api.publishEvent(id, nextPublished),
      () =>
        updateGroup(id, (g) => ({
          ...g,
          event: {
            ...g.event,
            publish_status: nextPublished ? "published" : "unpublished",
          },
        }))
    );

  const cancelEvt = (id: string) =>
    runAction(
      `${eventKey(id)}:cancel`,
      () => api.cancelEvent(id),
      () =>
        // cancel_event cascades `cancelled` to every occurrence — mirror that.
        updateGroup(id, (g) => ({
          ...g,
          event: { ...g.event, lifecycle_cancelled: true },
          subevents: g.subevents.map((s) => ({ ...s, lifecycle_cancelled: true })),
        }))
    );

  const deleteEvt = (id: string) =>
    runAction(
      `${eventKey(id)}:delete`,
      () => api.deleteEvent(id, true),
      () => {
        setPendingDeleteId(null);
        setGroups((prev) => prev.filter((g) => g.event.event_id !== id));
      }
    );

  // ─── occurrence (sub-event) row actions ──────────────────────────────────
  const reviewSub = (parentId: string, subId: string, status: string) =>
    runAction(
      `${subKey(subId)}:review`,
      () => api.reviewSub(parentId, subId, status),
      () =>
        updateGroup(parentId, (g) => ({
          ...g,
          subevents: g.subevents.map((s) =>
            s.subevent_id === subId ? { ...s, review_status: status } : s
          ),
        }))
    );

  const publishSub = (parentId: string, subId: string, nextPublished: boolean) =>
    runAction(
      `${subKey(subId)}:publish`,
      () => api.publishSub(parentId, subId, nextPublished),
      () =>
        updateGroup(parentId, (g) => ({
          ...g,
          subevents: g.subevents.map((s) =>
            s.subevent_id === subId
              ? { ...s, publish_status: nextPublished ? "published" : "unpublished" }
              : s
          ),
        }))
    );

  const deleteSub = (parentId: string, subId: string) =>
    runAction(
      `${subKey(subId)}:delete`,
      () => api.deleteSub(parentId, subId),
      () => {
        setPendingDeleteSubId(null);
        updateGroup(parentId, (g) => ({
          ...g,
          subevents: g.subevents.filter((s) => s.subevent_id !== subId),
        }));
      }
    );

  // ─── bulk review (actionable pending parents only) ───────────────────────
  const bulkReview = (status: string) => {
    const ids = [...selected];
    return runAction(
      `bulk:${status}`,
      () => api.bulkReview(ids, status),
      () => {
        setGroups((prev) =>
          prev
            .map((g) =>
              ids.includes(g.event.event_id)
                ? {
                    ...g,
                    event: { ...g.event, review_status: status },
                    parent_matches: status === review,
                  }
                : g
            )
            .filter(groupVisible)
        );
        setSelected(new Set());
      }
    );
  };

  // Parents the admin can bulk-act on: own status matches the pending tab.
  const selectableIds = groups
    .filter((g) => g.parent_matches && review === "pending")
    .map((g) => g.event.event_id);
  const toggleSelect = (id: string) =>
    setSelected((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const labelWithSpinner = (label: string, key: string) => (
    <>
      {isBusy(key) && <Loader2 size={14} className="animate-spin" />}
      {label}
    </>
  );

  return (
    <div className="flex flex-col gap-4">
      <SubTabs tabs={REVIEW_TABS} value={review} onChange={setReview} />
      {review === "pending" && selected.size > 0 && (
        <div className="flex gap-2">
          <Button
            variant="primary"
            disabled={busy !== null}
            onClick={() => void bulkReview("approved")}
          >
            {labelWithSpinner(`Approve ${selected.size}`, "bulk:approved")}
          </Button>
          <Button
            variant="danger"
            disabled={busy !== null}
            onClick={() => void bulkReview("rejected")}
          >
            {labelWithSpinner(`Reject ${selected.size}`, "bulk:rejected")}
          </Button>
        </div>
      )}

      {error && <ErrorBanner message={error} />}

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : groups.length === 0 ? (
        <p className="py-12 text-center text-sm text-[var(--color-text-muted)]">
          Nothing {review}.
        </p>
      ) : (
        <ul className="border-t border-[var(--color-rule)]">
          {groups.map((g) => {
            const ev = g.event;
            const id = ev.event_id;
            const rowKey = eventKey(id);
            const locked = rowBusy(rowKey);
            // Parent surfaced only for context (its own state differs from the
            // tab) — shown muted with no actions; you act on the occurrences.
            const contextOnly = !g.parent_matches;
            return (
              <li
                key={id}
                className="flex flex-col gap-3 border-b border-[var(--color-border)] py-4"
              >
                {/* ── parent header ── */}
                <div
                  className={`flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between ${
                    contextOnly ? "opacity-60" : ""
                  }`}
                >
                  <div className="flex min-w-0 items-start gap-3">
                    {!contextOnly && review === "pending" && (
                      <input
                        type="checkbox"
                        checked={selected.has(id)}
                        onChange={() => toggleSelect(id)}
                        className="mt-1.5 h-4 w-4 shrink-0 accent-[var(--color-primary)]"
                      />
                    )}
                    <div className="min-w-0">
                      <div className="font-serif text-base text-[var(--color-text-primary)]">
                        {ev.title || "Untitled"}
                        {ev.edited && (
                          <span className="ml-2 text-[11px] text-[var(--color-text-muted)]">
                            edited
                          </span>
                        )}
                        {contextOnly && (
                          <span className="ml-2 text-[11px] text-[var(--color-text-muted)]">
                            shown for context · {ev.review_status}
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-muted)]">
                        {ev.start_date && <span>{formatDate(ev.start_date)}</span>}
                        {ev.review_status && <Badge value={ev.review_status} />}
                        {ev.publish_status && <Badge value={ev.publish_status} />}
                        {ev.lifecycle_cancelled && <Badge value="cancelled" />}
                      </div>
                      {ev.description_md && (
                        <p className="mt-1.5 text-sm leading-relaxed text-[var(--color-text-secondary)]">
                          {truncate(ev.description_md, 160)}
                        </p>
                      )}
                    </div>
                  </div>

                  {!contextOnly && (
                    <div className="flex flex-wrap gap-1.5">
                      <Link to={`/admin/events/${encodeURIComponent(id)}/preview`}>
                        <Button>Preview</Button>
                      </Link>
                      {ev.review_status !== "approved" && (
                        <Button
                          disabled={locked}
                          onClick={() => void reviewEvt(id, "approved")}
                        >
                          {labelWithSpinner("Approve", `${rowKey}:review`)}
                        </Button>
                      )}
                      {ev.review_status !== "rejected" && (
                        <Button
                          disabled={locked}
                          onClick={() => void reviewEvt(id, "rejected")}
                        >
                          {labelWithSpinner("Reject", `${rowKey}:review`)}
                        </Button>
                      )}
                      <Button
                        disabled={locked}
                        onClick={() => void publishEvt(id, ev.publish_status !== "published")}
                      >
                        {labelWithSpinner(
                          ev.publish_status === "published" ? "Unpublish" : "Publish",
                          `${rowKey}:publish`
                        )}
                      </Button>
                      <Button disabled={locked} onClick={() => void cancelEvt(id)}>
                        {labelWithSpinner("Cancel", `${rowKey}:cancel`)}
                      </Button>
                      <Button
                        variant="danger"
                        disabled={locked}
                        onClick={() => setPendingDeleteId(id)}
                      >
                        Delete
                      </Button>
                    </div>
                  )}
                </div>

                {pendingDeleteId === id && (
                  <div className="flex flex-col gap-2 border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm text-[var(--color-text-secondary)] sm:flex-row sm:items-center sm:justify-between">
                    <span>
                      Delete &ldquo;{ev.title || "Untitled"}&rdquo;? Permanently removes the
                      event and its occurrences.
                    </span>
                    <div className="flex shrink-0 gap-2">
                      <Button variant="danger" disabled={locked} onClick={() => void deleteEvt(id)}>
                        {labelWithSpinner("Delete", `${rowKey}:delete`)}
                      </Button>
                      <Button onClick={() => setPendingDeleteId(null)}>Cancel</Button>
                    </div>
                  </div>
                )}

                {/* ── occurrences, always nested under their parent ── */}
                {g.subevents.length > 0 && (
                  <ul className="ml-3 flex flex-col gap-2 border-l border-[var(--color-border)] pl-4">
                    {g.subevents.map((sub) => {
                      const subRowKey = subKey(sub.subevent_id);
                      const subLocked = rowBusy(subRowKey);
                      return (
                        <li key={sub.subevent_id} className="flex flex-col gap-2">
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                            <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-muted)]">
                              <span className="text-[var(--color-text-secondary)]">
                                ↳ occurrence
                              </span>
                              {sub.start_date && <span>{formatDate(sub.start_date)}</span>}
                              {sub.review_status && <Badge value={sub.review_status} />}
                              {sub.publish_status && <Badge value={sub.publish_status} />}
                              {sub.lifecycle_cancelled && <Badge value="cancelled" />}
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {sub.review_status !== "approved" && (
                                <Button
                                  disabled={subLocked}
                                  onClick={() =>
                                    void reviewSub(id, sub.subevent_id, "approved")
                                  }
                                >
                                  {labelWithSpinner("Approve", `${subRowKey}:review`)}
                                </Button>
                              )}
                              {sub.review_status !== "rejected" && (
                                <Button
                                  disabled={subLocked}
                                  onClick={() =>
                                    void reviewSub(id, sub.subevent_id, "rejected")
                                  }
                                >
                                  {labelWithSpinner("Reject", `${subRowKey}:review`)}
                                </Button>
                              )}
                              <Button
                                disabled={subLocked}
                                onClick={() =>
                                  void publishSub(
                                    id,
                                    sub.subevent_id,
                                    sub.publish_status !== "published"
                                  )
                                }
                              >
                                {labelWithSpinner(
                                  sub.publish_status === "published" ? "Unpublish" : "Publish",
                                  `${subRowKey}:publish`
                                )}
                              </Button>
                              <Button
                                variant="danger"
                                disabled={subLocked}
                                onClick={() => setPendingDeleteSubId(sub.subevent_id)}
                              >
                                Delete
                              </Button>
                            </div>
                          </div>

                          {pendingDeleteSubId === sub.subevent_id && (
                            <div className="flex flex-col gap-2 border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm text-[var(--color-text-secondary)] sm:flex-row sm:items-center sm:justify-between">
                              <span>Delete this occurrence? Permanently removes the sub-event.</span>
                              <div className="flex shrink-0 gap-2">
                                <Button
                                  variant="danger"
                                  disabled={subLocked}
                                  onClick={() => void deleteSub(id, sub.subevent_id)}
                                >
                                  {labelWithSpinner("Delete", `${subRowKey}:delete`)}
                                </Button>
                                <Button onClick={() => setPendingDeleteSubId(null)}>Cancel</Button>
                              </div>
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {cursor && (
        <Button onClick={() => void loadMore()} disabled={loadingMore}>
          {loadingMore ? "Loading…" : "Load more"}
        </Button>
      )}

      {selectableIds.length > 0 && review === "pending" && (
        <button
          onClick={() => setSelected(new Set(selectableIds))}
          className="eyebrow self-start text-[var(--color-text-secondary)] underline-offset-4 hover:text-[var(--color-text-primary)] hover:underline"
        >
          Select all events
        </button>
      )}
    </div>
  );
}
