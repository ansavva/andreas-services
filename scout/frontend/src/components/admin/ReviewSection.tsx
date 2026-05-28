import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "@/api";
import { Badge, Button, ErrorBanner, Spinner, SubTabs } from "@/components/ui";
import { formatDate, truncate } from "@/utils/formatters";
import type { AdminEvent } from "@/types";

const REVIEWS = ["pending", "approved", "rejected"] as const;
const REVIEW_TABS = REVIEWS.map((r) => ({ key: r, label: r }));

// Row-scoped busy keys so the per-button spinner and the "disable siblings"
// check share the same prefix. Events use evt:<id>, sub-events sub:<id>.
const eventKey = (id: string) => `evt:${id}`;
const subKey = (id: string) => `sub:${id}`;

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

  const [items, setItems] = useState<AdminEvent[]>([]);
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

  const refresh = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      if (!silent) setError(null);
      try {
        const data = await api.listEvents(review);
        setItems(data.events);
        setCursor(data.next_cursor);
        if (!silent) setSelected(new Set());
      } catch (err) {
        if (!silent) setError(err instanceof Error ? err.message : "Failed to load");
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [api, review]
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const loadMore = async () => {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const data = await api.listEvents(review, cursor);
      setItems((prev) => [...prev, ...data.events]);
      setCursor(data.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load more");
    } finally {
      setLoadingMore(false);
    }
  };

  const isSub = (it: AdminEvent) => it.entity_type === "subevent";
  const isBusy = (key: string) => busy === key;
  const rowBusy = (rowKey: string) => busy?.startsWith(`${rowKey}:`) ?? false;

  // Runs an action with per-button spinner + row lock, applies an optimistic
  // local update on success, then quietly re-reads the page so server-side
  // cascades (e.g. cancel-parent flipping its sub-events) catch up. Errors
  // surface on the row's section-level banner; local state isn't mutated.
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
      void refresh(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(null);
    }
  };

  // ─── event row actions ───────────────────────────────────────────────────
  const reviewEvt = (id: string, status: string) =>
    runAction(
      `${eventKey(id)}:review`,
      () => api.reviewEvent(id, status),
      () => setItems((prev) => prev.filter((i) => isSub(i) || i.event_id !== id))
    );

  const publishEvt = (id: string, nextPublished: boolean) =>
    runAction(
      `${eventKey(id)}:publish`,
      () => api.publishEvent(id, nextPublished),
      () =>
        setItems((prev) =>
          prev.map((i) =>
            !isSub(i) && i.event_id === id
              ? { ...i, publish_status: nextPublished ? "published" : "unpublished" }
              : i
          )
        )
    );

  const cancelEvt = (id: string) =>
    runAction(
      `${eventKey(id)}:cancel`,
      () => api.cancelEvent(id),
      () =>
        setItems((prev) =>
          prev.map((i) =>
            !isSub(i) && i.event_id === id ? { ...i, lifecycle_cancelled: true } : i
          )
        )
      // verify() picks up the cascade to any sub-events visible in this view.
    );

  const deleteEvt = (id: string) =>
    runAction(
      `${eventKey(id)}:delete`,
      () => api.deleteEvent(id, true),
      () => {
        setPendingDeleteId(null);
        setItems((prev) =>
          prev.filter(
            (i) =>
              !(i.event_id === id && !isSub(i)) && // parent
              !(isSub(i) && i.parent_event_id === id) // its visible subs
          )
        );
      }
    );

  // ─── sub-event row actions ───────────────────────────────────────────────
  const reviewSub = (parentId: string, subId: string, status: string) =>
    runAction(
      `${subKey(subId)}:review`,
      () => api.reviewSub(parentId, subId, status),
      () => setItems((prev) => prev.filter((i) => !isSub(i) || i.subevent_id !== subId))
    );

  const publishSub = (parentId: string, subId: string, nextPublished: boolean) =>
    runAction(
      `${subKey(subId)}:publish`,
      () => api.publishSub(parentId, subId, nextPublished),
      () =>
        setItems((prev) =>
          prev.map((i) =>
            isSub(i) && i.subevent_id === subId
              ? { ...i, publish_status: nextPublished ? "published" : "unpublished" }
              : i
          )
        )
    );

  const deleteSub = (parentId: string, subId: string) =>
    runAction(
      `${subKey(subId)}:delete`,
      () => api.deleteSub(parentId, subId),
      () => {
        setPendingDeleteSubId(null);
        setItems((prev) => prev.filter((i) => !isSub(i) || i.subevent_id !== subId));
      }
    );

  // ─── bulk review ─────────────────────────────────────────────────────────
  const bulkReview = (status: string) => {
    const ids = [...selected];
    return runAction(
      `bulk:${status}`,
      () => api.bulkReview(ids, status),
      () => {
        setItems((prev) =>
          prev.filter((i) => isSub(i) || !ids.includes(i.event_id))
        );
        setSelected(new Set());
      }
    );
  };

  const eventIds = items.filter((i) => !isSub(i)).map((i) => i.event_id);
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
      ) : items.length === 0 ? (
        <p className="py-12 text-center text-sm text-[var(--color-text-muted)]">
          Nothing {review}.
        </p>
      ) : (
        <ul className="border-t border-[var(--color-rule)]">
          {items.map((it) => {
            const id = it.event_id;
            const sub = isSub(it);
            const rowKey = sub ? subKey(it.subevent_id ?? "") : eventKey(id);
            const liKey = sub ? `sub-${it.subevent_id}` : id;
            const locked = rowBusy(rowKey);
            return (
              <li
                key={liKey}
                className="flex flex-col gap-3 border-b border-[var(--color-border)] py-4"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex min-w-0 items-start gap-3">
                    {!sub && review === "pending" && (
                      <input
                        type="checkbox"
                        checked={selected.has(id)}
                        onChange={() => toggleSelect(id)}
                        className="mt-1.5 h-4 w-4 shrink-0 accent-[var(--color-primary)]"
                      />
                    )}
                    <div className="min-w-0">
                      <div className="font-serif text-base text-[var(--color-text-primary)]">
                        {sub ? "↳ occurrence" : it.title || "Untitled"}
                        {it.edited && (
                          <span className="ml-2 text-[11px] text-[var(--color-text-muted)]">
                            edited
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-muted)]">
                        {it.start_date && <span>{formatDate(it.start_date)}</span>}
                        {it.review_status && <Badge value={it.review_status} />}
                        {it.publish_status && <Badge value={it.publish_status} />}
                        {it.lifecycle_cancelled && <Badge value="cancelled" />}
                      </div>
                      {!sub && it.description_md && (
                        <p className="mt-1.5 text-sm leading-relaxed text-[var(--color-text-secondary)]">
                          {truncate(it.description_md, 160)}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-1.5">
                    {sub ? (
                      <>
                        <Button
                          disabled={locked}
                          onClick={() =>
                            void reviewSub(
                              it.parent_event_id ?? "",
                              it.subevent_id ?? "",
                              "approved"
                            )
                          }
                        >
                          {labelWithSpinner("Approve", `${rowKey}:review`)}
                        </Button>
                        <Button
                          disabled={locked}
                          onClick={() =>
                            void publishSub(
                              it.parent_event_id ?? "",
                              it.subevent_id ?? "",
                              it.publish_status !== "published"
                            )
                          }
                        >
                          {labelWithSpinner(
                            it.publish_status === "published" ? "Unpublish" : "Publish",
                            `${rowKey}:publish`
                          )}
                        </Button>
                        <Button
                          variant="danger"
                          disabled={locked}
                          onClick={() => setPendingDeleteSubId(it.subevent_id ?? "")}
                        >
                          Delete
                        </Button>
                      </>
                    ) : (
                      <>
                        <Link to={`/admin/events/${encodeURIComponent(id)}/preview`}>
                          <Button>Preview</Button>
                        </Link>
                        {it.review_status !== "approved" && (
                          <Button
                            disabled={locked}
                            onClick={() => void reviewEvt(id, "approved")}
                          >
                            {labelWithSpinner("Approve", `${rowKey}:review`)}
                          </Button>
                        )}
                        {it.review_status !== "rejected" && (
                          <Button
                            disabled={locked}
                            onClick={() => void reviewEvt(id, "rejected")}
                          >
                            {labelWithSpinner("Reject", `${rowKey}:review`)}
                          </Button>
                        )}
                        <Button
                          disabled={locked}
                          onClick={() =>
                            void publishEvt(id, it.publish_status !== "published")
                          }
                        >
                          {labelWithSpinner(
                            it.publish_status === "published" ? "Unpublish" : "Publish",
                            `${rowKey}:publish`
                          )}
                        </Button>
                        <Button
                          disabled={locked}
                          onClick={() => void cancelEvt(id)}
                        >
                          {labelWithSpinner("Cancel", `${rowKey}:cancel`)}
                        </Button>
                        <Button
                          variant="danger"
                          disabled={locked}
                          onClick={() => setPendingDeleteId(id)}
                        >
                          Delete
                        </Button>
                      </>
                    )}
                  </div>
                </div>

                {!sub && pendingDeleteId === id && (
                  <div className="flex flex-col gap-2 border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm text-[var(--color-text-secondary)] sm:flex-row sm:items-center sm:justify-between">
                    <span>
                      Delete &ldquo;{it.title || "Untitled"}&rdquo;? Permanently removes the
                      event and its sub-events.
                    </span>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        variant="danger"
                        disabled={locked}
                        onClick={() => void deleteEvt(id)}
                      >
                        {labelWithSpinner("Delete", `${rowKey}:delete`)}
                      </Button>
                      <Button onClick={() => setPendingDeleteId(null)}>Cancel</Button>
                    </div>
                  </div>
                )}

                {sub && pendingDeleteSubId === it.subevent_id && (
                  <div className="flex flex-col gap-2 border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm text-[var(--color-text-secondary)] sm:flex-row sm:items-center sm:justify-between">
                    <span>Delete this occurrence? Permanently removes the sub-event.</span>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        variant="danger"
                        disabled={locked}
                        onClick={() =>
                          void deleteSub(it.parent_event_id ?? "", it.subevent_id ?? "")
                        }
                      >
                        {labelWithSpinner("Delete", `${rowKey}:delete`)}
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

      {cursor && (
        <Button onClick={() => void loadMore()} disabled={loadingMore}>
          {loadingMore ? "Loading…" : "Load more"}
        </Button>
      )}

      {eventIds.length > 0 && review === "pending" && (
        <button
          onClick={() => setSelected(new Set(eventIds))}
          className="eyebrow self-start text-[var(--color-text-secondary)] underline-offset-4 hover:text-[var(--color-text-primary)] hover:underline"
        >
          Select all events
        </button>
      )}
    </div>
  );
}
