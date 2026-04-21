import { useState } from "react";
import { Calendar, DollarSign, ExternalLink, MapPin } from "lucide-react";
import type { Event } from "@/types";
import { displayUrl, formatDate, isUpcoming, truncate } from "@/utils/formatters";

interface EventCardProps {
  event: Event;
}

export function EventCard({ event }: EventCardProps) {
  const upcoming = isUpcoming(event.date);
  const [expanded, setExpanded] = useState(false);
  const description = event.description ?? "";
  const isLong = description.length > 160;
  const displayDesc = expanded ? description : truncate(description, 160);

  return (
    <article className="theme-transition flex flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-card hover:shadow-card-hover transition-shadow p-5 gap-3">
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-base font-semibold text-[var(--color-text-primary)] leading-snug flex-1">
          {event.event_name || "Untitled Event"}
        </h2>
        {upcoming && (
          <span className="shrink-0 text-xs font-medium px-2 py-0.5 rounded-full bg-[var(--color-badge)] text-[var(--color-badge-text)]">
            Upcoming
          </span>
        )}
      </div>

      <dl className="flex flex-col gap-1.5 text-sm text-[var(--color-text-secondary)]">
        {event.date && (
          <div className="flex items-center gap-2">
            <Calendar size={14} className="shrink-0 text-[var(--color-text-muted)]" />
            <dd>
              {formatDate(event.date)}
              {event.time ? ` · ${event.time}` : ""}
            </dd>
          </div>
        )}
        {event.venue && (
          <div className="flex items-center gap-2">
            <MapPin size={14} className="shrink-0 text-[var(--color-text-muted)]" />
            <dd>{event.venue}</dd>
          </div>
        )}
        {event.price && (
          <div className="flex items-center gap-2">
            <DollarSign size={14} className="shrink-0 text-[var(--color-text-muted)]" />
            <dd>{event.price}</dd>
          </div>
        )}
      </dl>

      {description && (
        <div className="text-sm text-[var(--color-text-secondary)] leading-relaxed">
          <p>{displayDesc}</p>
          {isLong && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="mt-1 text-[var(--color-primary)] hover:underline text-xs"
            >
              {expanded ? "Show less" : "Show more"}
            </button>
          )}
        </div>
      )}

      {event.links && event.links.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-auto pt-2 border-t border-[var(--color-border)]">
          {event.links.slice(0, 3).map((url, i) => (
            <a
              key={i}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-[var(--color-primary)] hover:text-[var(--color-primary-hover)] hover:underline"
            >
              <ExternalLink size={11} />
              {displayUrl(url)}
            </a>
          ))}
        </div>
      )}
    </article>
  );
}
