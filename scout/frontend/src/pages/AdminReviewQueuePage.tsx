import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "@/api";
import { SwipeCard, type Decision } from "@/components/admin/SwipeCard";
import { ErrorBanner, Spinner } from "@/components/ui";
import type { PublicEvent, ReviewGroup } from "@/types";

// Prefetch the next card's preview this far ahead, and pull another page when
// the deck runs this low.
const PREFETCH_AHEAD = 1;
const LOAD_MORE_AT = 3;

/**
 * Full-screen swipe review of the pending queue. Each card previews an event
 * exactly as the public detail page renders it; swiping right approves +
 * publishes the event and all its occurrences, left rejects + unpublishes them.
 * A back control re-visits the previous card so a reviewer can change their mind
 * (re-deciding overwrites). The deck only carries genuinely-pending parents.
 */
export function AdminReviewQueuePage() {
  const api = useApi();
  const [deck, setDeck] = useState<ReviewGroup[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [previews, setPreviews] = useState<Record<string, PublicEvent>>({});
  const [previewErrors, setPreviewErrors] = useState<Record<string, string>>({});
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [feedbacks, setFeedbacks] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The pending tab surfaces some parents only for context (already approved,
  // with a pending occurrence). The swipe deck is an inbox of decisions to make,
  // so we keep only parents whose own status is pending.
  const actionable = (groups: ReviewGroup[]) => groups.filter((g) => g.parent_matches);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listEvents("pending");
      setDeck(actionable(data.groups));
      setCursor(data.next_cursor);
      setIndex(0);
      setDecisions({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the queue");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const data = await api.listEvents("pending", cursor);
      const seen = new Set(deck.map((g) => g.event.event_id));
      setDeck((prev) => [
        ...prev,
        ...actionable(data.groups).filter((g) => !seen.has(g.event.event_id)),
      ]);
      setCursor(data.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load more");
    } finally {
      setLoadingMore(false);
    }
  }, [api, cursor, loadingMore, deck]);

  // Pull the next page while the reviewer still has cards in hand.
  useEffect(() => {
    if (cursor && deck.length - index <= LOAD_MORE_AT) void loadMore();
  }, [cursor, deck.length, index, loadMore]);

  // Fetch the current card's preview (and one ahead) on demand, once each.
  const pending = useRef(new Set<string>());
  useEffect(() => {
    for (let i = index; i <= index + PREFETCH_AHEAD && i < deck.length; i++) {
      const id = deck[i].event.event_id;
      if (previews[id] || previewErrors[id] || pending.current.has(id)) continue;
      pending.current.add(id);
      api
        .previewEvent(id)
        .then((e) => setPreviews((prev) => ({ ...prev, [id]: e })))
        .catch((err) =>
          setPreviewErrors((prev) => ({
            ...prev,
            [id]: err instanceof Error ? err.message : "Not found",
          }))
        )
        .finally(() => pending.current.delete(id));
    }
  }, [index, deck, previews, previewErrors, api]);

  const current = deck[index];

  const decide = async (decision: Decision) => {
    if (!current) return;
    const id = current.event.event_id;
    setBusy(true);
    setError(null);
    try {
      await api.decideEvent(id, decision, feedbacks[id]?.trim() || undefined);
      setDecisions((prev) => ({ ...prev, [id]: decision }));
      setIndex((i) => i + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save your decision");
    } finally {
      setBusy(false);
    }
  };

  const goBack = () => {
    if (index > 0) setIndex((i) => i - 1);
  };

  const total = deck.length;
  const done = !loading && current === undefined;

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <header className="sticky top-0 z-10 border-b border-[var(--color-rule)] bg-[var(--color-surface)]">
        <div className="mx-auto flex max-w-2xl items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <Link
            to="/admin?tab=review"
            className="eyebrow text-[var(--color-text-secondary)] no-underline hover:text-[var(--color-text-primary)] hover:underline"
          >
            ← Review queue
          </Link>
          <span className="eyebrow text-[var(--color-text-muted)]">
            {total === 0 ? "Swipe review" : `${Math.min(index + 1, total)} of ${total}${cursor ? "+" : ""}`}
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-5 py-8 sm:px-6">
        {error && (
          <div className="mb-5">
            <ErrorBanner message={error} />
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-24">
            <Spinner />
          </div>
        ) : done ? (
          <div className="py-24 text-center">
            <p className="font-serif text-2xl font-light text-[var(--color-text-primary)]">
              All caught up
            </p>
            <p className="mt-2 text-sm text-[var(--color-text-muted)]">
              Nothing left to review.
            </p>
            <button
              onClick={() => void refresh()}
              className="eyebrow mt-6 text-[var(--color-text-secondary)] underline-offset-4 hover:text-[var(--color-text-primary)] hover:underline"
            >
              Refresh queue
            </button>
          </div>
        ) : (
          current && (
            <SwipeCard
              key={current.event.event_id}
              group={current}
              preview={previews[current.event.event_id] ?? null}
              previewError={previewErrors[current.event.event_id] ?? null}
              priorDecision={decisions[current.event.event_id]}
              feedback={feedbacks[current.event.event_id] ?? ""}
              onFeedbackChange={(value) =>
                setFeedbacks((prev) => ({ ...prev, [current.event.event_id]: value }))
              }
              onDecide={(d) => void decide(d)}
              onBack={goBack}
              canGoBack={index > 0}
              busy={busy}
            />
          )
        )}
      </main>
    </div>
  );
}
