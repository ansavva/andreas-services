import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "@/api";
import { EventDetailView } from "@/components/EventDetailView";
import { Badge, Button, ErrorBanner, Spinner, SubTabs } from "@/components/ui";
import { formatDate, truncate } from "@/utils/formatters";
import type { AdminEvent, PublicEvent } from "@/types";

const REVIEWS = ["pending", "approved", "rejected"] as const;
const REVIEW_TABS = REVIEWS.map((r) => ({ key: r, label: r }));

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
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openPreview, setOpenPreview] = useState<string | null>(null);
  const [previews, setPreviews] = useState<Record<string, PublicEvent>>({});
  const [previewLoading, setPreviewLoading] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    setOpenPreview(null);
    setPreviews({});
    try {
      const data = await api.listEvents(review);
      setItems(data.events);
      setSelected(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [api, review]);

  const togglePreview = useCallback(
    async (id: string) => {
      if (openPreview === id) {
        setOpenPreview(null);
        return;
      }
      setOpenPreview(id);
      setPreviewError(null);
      if (previews[id]) return;
      setPreviewLoading(id);
      try {
        const data = await api.previewEvent(id);
        setPreviews((p) => ({ ...p, [id]: data }));
      } catch (err) {
        setPreviewError(err instanceof Error ? err.message : "Preview failed");
      } finally {
        setPreviewLoading(null);
      }
    },
    [api, openPreview, previews]
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const isSub = (it: AdminEvent) => it.entity_type === "subevent";

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    }
  };

  const eventIds = items.filter((i) => !isSub(i)).map((i) => i.event_id);
  const toggleSelect = (id: string) =>
    setSelected((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  return (
    <div className="flex flex-col gap-4">
      <SubTabs tabs={REVIEW_TABS} value={review} onChange={setReview} />
      {review === "pending" && selected.size > 0 && (
        <div className="flex gap-2">
          <Button
            variant="primary"
            onClick={() => void act(() => api.bulkReview([...selected], "approved"))}
          >
            Approve {selected.size}
          </Button>
          <Button
            variant="danger"
            onClick={() => void act(() => api.bulkReview([...selected], "rejected"))}
          >
            Reject {selected.size}
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
            const key = sub ? `sub-${it.subevent_id}` : id;
            return (
              <li
                key={key}
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
                        onClick={() =>
                          void act(() =>
                            api.reviewSub(it.parent_event_id ?? "", it.subevent_id ?? "", "approved")
                          )
                        }
                      >
                        Approve
                      </Button>
                      <Button
                        onClick={() =>
                          void act(() =>
                            api.publishSub(
                              it.parent_event_id ?? "",
                              it.subevent_id ?? "",
                              it.publish_status !== "published"
                            )
                          )
                        }
                      >
                        {it.publish_status === "published" ? "Unpublish" : "Publish"}
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button onClick={() => void togglePreview(id)}>
                        {openPreview === id ? "Hide" : "Preview"}
                      </Button>
                      {it.review_status !== "approved" && (
                        <Button onClick={() => void act(() => api.reviewEvent(id, "approved"))}>
                          Approve
                        </Button>
                      )}
                      {it.review_status !== "rejected" && (
                        <Button onClick={() => void act(() => api.reviewEvent(id, "rejected"))}>
                          Reject
                        </Button>
                      )}
                      <Button
                        onClick={() =>
                          void act(() => api.publishEvent(id, it.publish_status !== "published"))
                        }
                      >
                        {it.publish_status === "published" ? "Unpublish" : "Publish"}
                      </Button>
                      <Button onClick={() => void act(() => api.cancelEvent(id))}>Cancel</Button>
                      <Button
                        variant="danger"
                        onClick={() => void act(() => api.deleteEvent(id, true))}
                      >
                        Delete
                      </Button>
                    </>
                  )}
                </div>
                </div>

                {!sub && openPreview === id && (
                  <div className="border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-6 sm:px-6 sm:py-8">
                    {previewLoading === id ? (
                      <div className="flex justify-center py-8">
                        <Spinner />
                      </div>
                    ) : previewError ? (
                      <ErrorBanner message={previewError} />
                    ) : previews[id] ? (
                      <EventDetailView event={previews[id]} />
                    ) : null}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
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
