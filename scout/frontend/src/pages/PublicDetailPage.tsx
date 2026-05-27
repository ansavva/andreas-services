import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "@/api";
import { Header } from "@/components/Header";
import { Chip, ErrorBanner, Spinner } from "@/components/ui";
import { formatDate } from "@/utils/formatters";
import type { PublicEvent, PublicLocation, PublicSubEvent } from "@/types";

function locationLine(location: PublicLocation | null): string | null {
  if (!location) return null;
  return location.address ? `${location.name}, ${location.address}` : location.name;
}

function SubEventRow({ sub }: { sub: PublicSubEvent }) {
  return (
    <li className="border-b border-[var(--color-border)] py-5">
      <div className="font-serif text-lg leading-tight text-[var(--color-text-primary)]">
        {formatDate(sub.start_date)}
        {sub.start_time ? ` · ${sub.start_time}` : ""}
        {sub.end_time ? `–${sub.end_time}` : ""}
      </div>
      {locationLine(sub.location) && (
        <div className="eyebrow mt-2 text-[var(--color-text-secondary)]">
          {locationLine(sub.location)}
        </div>
      )}
      {sub.event_labels.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
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
  const place = event ? locationLine(event.location) : null;

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <Header />
      <main className="mx-auto max-w-3xl px-5 py-10 sm:px-6 sm:py-14">
        <Link
          to="/"
          className="eyebrow inline-flex items-center gap-2 text-[var(--color-text-muted)] no-underline hover:text-[var(--color-text-primary)]"
        >
          ← Back to the edit
        </Link>

        {loading && (
          <div className="flex justify-center py-24">
            <Spinner />
          </div>
        )}
        {error && <div className="mt-10"><ErrorBanner message={error} /></div>}

        {!loading && !error && event && (
          <article className="mt-10">
            {labels.length > 0 && (
              <p className="eyebrow text-[var(--color-text-muted)]">
                {labels.map((l) => l.name).join(" · ")}
              </p>
            )}

            <h1 className="mt-4 font-serif text-hero font-light text-[var(--color-text-primary)]">
              {event.title}
            </h1>

            <div className="eyebrow mt-6 flex flex-wrap items-center gap-x-3 gap-y-2 border-y border-[var(--color-rule)] py-4 text-[var(--color-text-secondary)]">
              {event.start_date && (
                <span>
                  {formatDate(event.start_date)}
                  {event.start_time ? ` · ${event.start_time}` : ""}
                </span>
              )}
              {event.start_date && place && <span aria-hidden>—</span>}
              {place && <span>{place}</span>}
            </div>

            {image && (
              <img
                src={image}
                alt={event.title}
                className="mt-8 aspect-[16/9] w-full object-cover grayscale"
              />
            )}

            {event.description && (
              <div className="mt-8 max-w-prose whitespace-pre-line text-base leading-relaxed text-[var(--color-text-secondary)] sm:text-lg">
                {event.description}
              </div>
            )}

            {event.sub_events.length > 0 ? (
              <section className="mt-12">
                <h2 className="eyebrow text-[var(--color-text-muted)]">Dates</h2>
                <ul className="mt-4 border-t border-[var(--color-rule)]">
                  {event.sub_events.map((s) => (
                    <SubEventRow key={s.subevent_id} sub={s} />
                  ))}
                </ul>
              </section>
            ) : event.no_upcoming_dates ? (
              <p className="mt-12 text-sm text-[var(--color-text-muted)]">No upcoming dates.</p>
            ) : null}
          </article>
        )}
      </main>
    </div>
  );
}
