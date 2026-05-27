import { Link } from "react-router-dom";
import type { PublicEvent } from "@/types";
import { formatDate, truncate } from "@/utils/formatters";

function firstImage(event: PublicEvent): string | null {
  const img = event.images.find((i) => i.url || i.s3_ref);
  return img?.url ?? null;
}

export function EventCard({ event }: { event: PublicEvent }) {
  const image = firstImage(event);
  const labels = [...event.event_labels, ...event.location_labels];
  const kicker = labels[0]?.name;
  const href = `/events/${event.event_id}`;

  return (
    <article className="group flex flex-col">
      <Link to={href} className="no-underline">
        <div className="aspect-[4/3] w-full overflow-hidden bg-[var(--color-surface-hover)]">
          {image && (
            <img
              src={image}
              alt={event.title}
              loading="lazy"
              className="h-full w-full object-cover grayscale transition-[filter] duration-700 ease-out group-hover:grayscale-0"
            />
          )}
        </div>
      </Link>

      <div className="flex flex-1 flex-col gap-2 pt-4">
        {kicker && (
          <span className="eyebrow text-[var(--color-text-muted)]">{kicker}</span>
        )}

        <Link to={href} className="no-underline">
          <h2 className="font-serif text-xl leading-tight text-[var(--color-text-primary)] underline-offset-4 group-hover:underline">
            {event.title || "Untitled event"}
          </h2>
        </Link>

        <div className="eyebrow flex flex-wrap items-center gap-x-2 gap-y-1 text-[var(--color-text-secondary)]">
          {event.start_date && (
            <span>
              {formatDate(event.start_date)}
              {event.start_time ? ` · ${event.start_time}` : ""}
            </span>
          )}
          {event.start_date && event.location && <span aria-hidden>—</span>}
          {event.location && <span>{event.location.name}</span>}
        </div>

        {event.description && (
          <p className="mt-1 text-sm leading-relaxed text-[var(--color-text-secondary)]">
            {truncate(event.description, 140)}
          </p>
        )}

        {event.sub_events.length > 0 && (
          <span className="eyebrow mt-auto pt-2 text-[var(--color-text-muted)]">
            {event.sub_events.length} upcoming date
            {event.sub_events.length === 1 ? "" : "s"}
          </span>
        )}
      </div>
    </article>
  );
}
