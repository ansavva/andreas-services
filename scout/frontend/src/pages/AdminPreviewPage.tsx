import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "@/api";
import { Header } from "@/components/Header";
import { EventDetailView } from "@/components/EventDetailView";
import { ErrorBanner, Spinner } from "@/components/ui";
import type { PublicEvent } from "@/types";

/**
 * Admin preview of an event rendered as a full page — what the public detail
 * page will look like once the event is published. Uses `previewEvent` so it
 * works for pending/unpublished events too and includes their unapproved
 * images.
 */
export function AdminPreviewPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const api = useApi();
  const [event, setEvent] = useState<PublicEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!eventId) return;
    setLoading(true);
    api
      .previewEvent(eventId)
      .then((e) => setEvent(e))
      .catch((err) => setError(err instanceof Error ? err.message : "Not found"))
      .finally(() => setLoading(false));
  }, [api, eventId]);

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <Header />
      <main className="mx-auto max-w-3xl px-5 py-10 sm:px-6 sm:py-14">
        <Link
          to="/admin?tab=review"
          className="eyebrow inline-flex items-center gap-2 text-[var(--color-text-muted)] no-underline hover:text-[var(--color-text-primary)]"
        >
          ← Back to review
        </Link>

        {loading && (
          <div className="flex justify-center py-24">
            <Spinner />
          </div>
        )}
        {error && (
          <div className="mt-10">
            <ErrorBanner message={error} />
          </div>
        )}

        {!loading && !error && event && (
          <div className="mt-10">
            <EventDetailView event={event} />
          </div>
        )}
      </main>
    </div>
  );
}
