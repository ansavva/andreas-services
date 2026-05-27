import { useCallback, useEffect, useState } from "react";
import { useApi } from "@/api";
import { Badge, Button, ErrorBanner, Spinner } from "@/components/ui";
import { formatDate } from "@/utils/formatters";
import type { AdminEvent } from "@/types";

const REVIEWS = ["pending", "approved", "rejected"] as const;

export function ReviewSection() {
  const api = useApi();
  const [review, setReview] = useState<string>("pending");
  const [items, setItems] = useState<AdminEvent[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
          {REVIEWS.map((r) => (
            <button
              key={r}
              onClick={() => setReview(r)}
              className={`shrink-0 whitespace-nowrap rounded-none px-3 py-2 text-[11px] font-medium uppercase tracking-[0.12em] transition-colors ${
                review === r
                  ? "bg-[var(--color-primary)] text-white"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
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
      </div>

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
                className="flex flex-col gap-3 border-b border-[var(--color-border)] py-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex items-start gap-3">
                  {!sub && review === "pending" && (
                    <input
                      type="checkbox"
                      checked={selected.has(id)}
                      onChange={() => toggleSelect(id)}
                      className="mt-1.5 h-4 w-4 shrink-0 accent-[var(--color-primary)]"
                    />
                  )}
                  <div>
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
