import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, CalendarDays, MapPin } from "lucide-react";
import { useApi } from "@/api";
import { Header } from "@/components/Header";
import { Chip, ErrorBanner, Spinner } from "@/components/ui";
import { formatDate } from "@/utils/formatters";
import type { PublicEvent, PublicLocation, PublicSubEvent } from "@/types";

function LocationLine({ location }: { location: PublicLocation | null }) {
  if (!location) return null;
  return (
    <div className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
      <MapPin size={15} className="shrink-0 text-[var(--color-primary)]" />
      <span>
        {location.name}
        {location.address ? ` — ${location.address}` : ""}
      </span>
    </div>
  );
}

function SubEventRow({ sub }: { sub: PublicSubEvent }) {
  return (
    <li className="rounded-lg border border-[var(--color-border)] p-3">
      <div className="flex items-center gap-2 text-sm font-medium text-[var(--color-text-primary)]">
        <CalendarDays size={14} className="text-[var(--color-primary)]" />
        {formatDate(sub.start_date)}
        {sub.start_time ? ` · ${sub.start_time}` : ""}
        {sub.end_time ? `–${sub.end_time}` : ""}
      </div>
      <div className="mt-1">
        <LocationLine location={sub.location} />
      </div>
      {sub.event_labels.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {sub.event_labels.map((l) => (
            <Chip key={l.id} label={l.name} />
          ))}
        </div>
      )}
    </li>
  );
}

export function PublicDetailPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const api = useApi();
  const [event, setEvent] = useState<PublicEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!eventId) return;
    setLoading(true);
    api
      .eventDetail(eventId)
      .then((e) => setEvent(e))
      .catch((err) => setError(err instanceof Error ? err.message : "Not found"))
      .finally(() => setLoading(false));
  }, [api, eventId]);

  const labels = event ? [...event.event_labels, ...event.location_labels] : [];
  const image = event?.images.find((i) => i.url)?.url ?? null;

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <Header />
      <main className="mx-auto max-w-3xl px-4 py-8">
        <Link
          to="/"
          className="mb-6 inline-flex items-center gap-1.5 text-sm text-[var(--color-text-muted)] no-underline hover:text-[var(--color-text-primary)]"
        >
          <ArrowLeft size={16} />
          All events
        </Link>

        {loading && (
          <div className="flex justify-center py-24">
            <Spinner />
          </div>
        )}
        {error && <ErrorBanner message={error} />}

        {!loading && !error && event && (
          <article className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-card">
            {image && <img src={image} alt={event.title} className="h-64 w-full object-cover" />}
            <div className="space-y-6 p-6 md:p-8">
              <h1 className="text-2xl font-bold leading-tight text-[var(--color-text-primary)]">
                {event.title}
              </h1>

              {labels.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {labels.map((l) => (
                    <Chip key={l.id} label={l.name} />
                  ))}
                </div>
              )}

              <div className="space-y-2">
                {event.start_date && (
                  <div className="flex items-center gap-2 text-sm font-medium text-[var(--color-text-secondary)]">
                    <CalendarDays size={15} className="shrink-0 text-[var(--color-primary)]" />
                    {formatDate(event.start_date)}
                    {event.start_time ? ` · ${event.start_time}` : ""}
                  </div>
                )}
                <LocationLine location={event.location} />
              </div>

              {event.description && (
                <p className="whitespace-pre-line text-sm leading-relaxed text-[var(--color-text-secondary)]">
                  {event.description}
                </p>
              )}

              {event.sub_events.length > 0 ? (
                <div>
                  <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                    Dates
                  </h2>
                  <ul className="flex flex-col gap-2">
                    {event.sub_events.map((s) => (
                      <SubEventRow key={s.subevent_id} sub={s} />
                    ))}
                  </ul>
                </div>
              ) : event.no_upcoming_dates ? (
                <p className="text-sm text-[var(--color-text-muted)]">No upcoming dates.</p>
              ) : null}
            </div>
          </article>
        )}
      </main>
    </div>
  );
}
