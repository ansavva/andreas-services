import { Link } from "react-router-dom";
import { ArrowUpRight, CalendarDays, MapPin } from "lucide-react";
import type { PublicEvent } from "@/types";
import { Chip } from "@/components/ui";
import { formatDate, truncate } from "@/utils/formatters";

function firstImage(event: PublicEvent): string | null {
  const img = event.images.find((i) => i.url || i.s3_ref);
  return img?.url ?? null;
}

export function EventCard({ event }: { event: PublicEvent }) {
  const image = firstImage(event);
  const labels = [...event.event_labels, ...event.location_labels];

  return (
    <article className="theme-transition flex flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-card transition-all hover:bg-[var(--color-surface-hover)]">
      {image && (
        <img src={image} alt={event.title} className="h-40 w-full object-cover" />
      )}
      <div className="flex flex-1 flex-col gap-3 p-5">
        <Link to={`/events/${event.event_id}`} className="group no-underline">
          <h2 className="inline-flex items-start gap-1 text-base font-semibold leading-snug text-[var(--color-text-primary)] transition-colors group-hover:text-[var(--color-primary)]">
            {event.title || "Untitled event"}
            <ArrowUpRight
              size={14}
              className="mt-0.5 shrink-0 text-[var(--color-primary)] opacity-0 transition-opacity group-hover:opacity-100"
            />
          </h2>
        </Link>

        <dl className="flex flex-col gap-1.5 text-sm text-[var(--color-text-secondary)]">
          {event.start_date && (
            <div className="flex items-center gap-2">
              <CalendarDays size={14} className="shrink-0 text-[var(--color-text-muted)]" />
              <dd>
                {formatDate(event.start_date)}
                {event.start_time ? ` · ${event.start_time}` : ""}
              </dd>
            </div>
          )}
          {event.location && (
            <div className="flex items-center gap-2">
              <MapPin size={14} className="shrink-0 text-[var(--color-text-muted)]" />
              <dd>{event.location.name}</dd>
            </div>
          )}
        </dl>

        {labels.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {labels.map((l) => (
              <Chip key={l.id} label={l.name} />
            ))}
          </div>
        )}

        {event.description && (
          <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
            {truncate(event.description, 160)}
          </p>
        )}

        {event.sub_events.length > 0 && (
          <p className="mt-auto pt-2 text-xs text-[var(--color-text-muted)]">
            {event.sub_events.length} upcoming date
            {event.sub_events.length === 1 ? "" : "s"}
          </p>
        )}
      </div>
    </article>
  );
}
