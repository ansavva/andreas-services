import { Chip } from "@/components/ui";
import { formatDate } from "@/utils/formatters";
import type { PublicEvent, PublicLocation, PublicSubEvent } from "@/types";

export function locationLine(location: PublicLocation | null): string | null {
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

/**
 * Presentational render of a single event in the public detail layout. Shared
 * by the public detail page and the admin inline preview so what an admin sees
 * matches the published page exactly.
 */
export function EventDetailView({ event }: { event: PublicEvent }) {
  const labels = [...event.event_labels, ...event.location_labels];
  const image = event.images.find((i) => i.url)?.url ?? null;
  const place = locationLine(event.location);

  return (
    <article>
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
  );
}
