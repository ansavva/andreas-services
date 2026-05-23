import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowUpRight, Calendar, DollarSign, ExternalLink, MapPin } from "lucide-react";
import type { Event } from "@/types";
import { displayUrl, formatDate, isUpcoming, truncate } from "@/utils/formatters";

interface EventCardProps {
  event: Event;
}

export function EventCard({ event }: EventCardProps) {
  const location = useLocation();
  const upcoming = isUpcoming(event.date);
  const [expanded, setExpanded] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);
  const description = event.description ?? "";
  const isLong = description.length > 160;
  const displayDesc = expanded ? description : truncate(description, 160);
  const showImage = !!event.image_url && !imgFailed;

  return (
    <article className="theme-transition flex flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-card hover:shadow-card-hover hover:bg-[var(--color-surface-hover)] transition-all overflow-hidden">
      {showImage && (
        <img
          src={event.image_url}
          alt={event.event_name}
          className="w-full h-40 object-cover"
          onError={() => setImgFailed(true)}
        />
      )}

      <div className="flex flex-col gap-3 p-5 flex-1">
        <div className="flex items-start justify-between gap-2">
          <Link
            to={`/events/${event.event_id}`}
            state={{ fromSearch: location.search }}
            className="flex-1 group"
          >
            <h2 className="text-base font-semibold text-[var(--color-text-primary)] leading-snug group-hover:text-[var(--color-primary)] transition-colors inline-flex items-start gap-1">
              {event.event_name || "Untitled Event"}
              <ArrowUpRight
                size={14}
                className="shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-primary)]"
              />
            </h2>
          </Link>
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
      </div>
    </article>
  );
}
