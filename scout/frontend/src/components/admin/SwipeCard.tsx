import { useEffect, useRef, useState } from "react";
import { Check, RotateCcw, X } from "lucide-react";
import { Link } from "react-router-dom";
import { EventDetailView } from "@/components/EventDetailView";
import { Spinner } from "@/components/ui";
import type { PublicEvent, ReviewGroup } from "@/types";

export type Decision = "approved" | "rejected";

// Past this horizontal travel (px) a release commits the decision; below it the
// card springs back to centre.
const COMMIT_THRESHOLD = 120;

/**
 * A single reviewable event rendered as a Tinder-style card. The whole card is
 * draggable horizontally (right = approve, left = reject); vertical drags scroll
 * the preview instead. The same decisions are available as buttons underneath so
 * the card works without gestures. A prior decision is shown so going back to
 * re-decide is unambiguous.
 */
export function SwipeCard({
  group,
  preview,
  previewError,
  priorDecision,
  feedback,
  onFeedbackChange,
  onDecide,
  onBack,
  canGoBack,
  busy,
}: {
  group: ReviewGroup;
  preview: PublicEvent | null;
  previewError: string | null;
  priorDecision?: Decision;
  feedback: string;
  onFeedbackChange: (value: string) => void;
  onDecide: (decision: Decision) => void;
  onBack: () => void;
  canGoBack: boolean;
  busy: boolean;
}) {
  // Live horizontal offset while dragging; `leaving` carries the card off-screen
  // on commit before the parent advances the deck.
  const [dragX, setDragX] = useState(0);
  const [leaving, setLeaving] = useState<Decision | null>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const horizontal = useRef(false);

  const occurrences = group.subevents.length;

  const commit = (decision: Decision) => {
    if (busy || leaving) return;
    setLeaving(decision);
  };

  // After the exit animation, hand the decision up. Keyed on `leaving` so each
  // commit fires exactly once.
  useEffect(() => {
    if (!leaving) return;
    const t = setTimeout(() => {
      onDecide(leaving);
      setLeaving(null);
      setDragX(0);
    }, 220);
    return () => clearTimeout(t);
  }, [leaving, onDecide]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (busy || leaving) return;
    start.current = { x: e.clientX, y: e.clientY };
    horizontal.current = false;
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!start.current) return;
    const dx = e.clientX - start.current.x;
    const dy = e.clientY - start.current.y;
    if (!horizontal.current) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
      // Lock to horizontal only when the gesture is clearly sideways; otherwise
      // let the preview scroll vertically.
      if (Math.abs(dx) <= Math.abs(dy)) {
        start.current = null;
        return;
      }
      horizontal.current = true;
      (e.target as Element).setPointerCapture?.(e.pointerId);
    }
    setDragX(dx);
  };

  const endDrag = () => {
    if (!start.current) {
      setDragX(0);
      return;
    }
    start.current = null;
    if (dragX > COMMIT_THRESHOLD) commit("approved");
    else if (dragX < -COMMIT_THRESHOLD) commit("rejected");
    else setDragX(0);
  };

  const offset = leaving ? (leaving === "approved" ? 1000 : -1000) : dragX;
  const intent: Decision | null =
    leaving ?? (dragX > 40 ? "approved" : dragX < -40 ? "rejected" : null);

  return (
    <div className="flex flex-col items-center gap-5">
      <div className="relative w-full" style={{ perspective: 1000 }}>
        <article
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          className="relative cursor-grab touch-pan-y select-none overflow-hidden border border-[var(--color-border)] bg-[var(--color-surface)] active:cursor-grabbing"
          style={{
            transform: `translateX(${offset}px) rotate(${offset * 0.03}deg)`,
            transition: start.current ? "none" : "transform 0.22s ease-out",
          }}
        >
          {/* Drag-intent watermark */}
          {intent && (
            <div
              className={`pointer-events-none absolute top-6 z-10 rounded-none border-2 px-3 py-1 text-sm font-semibold uppercase tracking-[0.2em] ${
                intent === "approved"
                  ? "left-6 rotate-[-12deg] border-[var(--color-primary)] text-[var(--color-primary)]"
                  : "right-6 rotate-[12deg] border-[var(--color-text-primary)] text-[var(--color-text-primary)]"
              }`}
            >
              {intent === "approved" ? "Approve" : "Reject"}
            </div>
          )}

          <div className="max-h-[58vh] overflow-y-auto px-5 py-6 sm:px-8 sm:py-8">
            <div className="mb-4 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
              <span>To review</span>
              {occurrences > 0 && (
                <span>
                  · {occurrences} occurrence{occurrences === 1 ? "" : "s"}
                </span>
              )}
              {priorDecision && (
                <span className="text-[var(--color-text-secondary)]">
                  · you {priorDecision} this — swipe again to change
                </span>
              )}
            </div>

            {previewError ? (
              <p className="py-10 text-center text-sm text-[var(--color-text-muted)]">
                Could not load preview: {previewError}
              </p>
            ) : preview ? (
              <EventDetailView event={preview} />
            ) : (
              <div className="flex justify-center py-16">
                <Spinner />
              </div>
            )}
          </div>
        </article>
      </div>

      <Link
        to={`/admin/events/${encodeURIComponent(group.event.event_id)}/preview`}
        className="eyebrow text-[var(--color-text-secondary)] no-underline hover:text-[var(--color-text-primary)] hover:underline"
      >
        Open full preview page →
      </Link>

      <textarea
        value={feedback}
        onChange={(e) => onFeedbackChange(e.target.value)}
        placeholder="Optional: why approve or reject? (saved with your decision)"
        rows={2}
        className="w-full resize-none border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-text-primary)] focus:outline-none"
      />

      {/* Button parity with the swipe gestures. */}
      <div className="flex items-center justify-center gap-4">
        <button
          type="button"
          disabled={busy || leaving !== null}
          onClick={() => commit("rejected")}
          title="Reject"
          className="flex h-14 w-14 items-center justify-center rounded-full border border-[var(--color-text-primary)] text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-text-primary)] hover:text-white disabled:opacity-40"
        >
          <X size={22} />
        </button>
        <button
          type="button"
          disabled={!canGoBack || busy || leaving !== null}
          onClick={onBack}
          title="Back to previous event"
          className="flex h-12 w-12 items-center justify-center rounded-full border border-[var(--color-border)] text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-text-primary)] hover:text-[var(--color-text-primary)] disabled:opacity-40"
        >
          <RotateCcw size={18} />
        </button>
        <button
          type="button"
          disabled={busy || leaving !== null}
          onClick={() => commit("approved")}
          title="Approve & publish"
          className="flex h-14 w-14 items-center justify-center rounded-full border border-[var(--color-primary)] bg-[var(--color-primary)] text-white transition-colors hover:bg-[var(--color-primary-hover)] disabled:opacity-40"
        >
          <Check size={22} />
        </button>
      </div>

      <p className="text-center text-xs text-[var(--color-text-muted)]">
        Approve publishes the event and all its occurrences. Reject unpublishes them.
      </p>
    </div>
  );
}
