import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Calendar,
  Check,
  ChevronDown,
  ChevronUp,
  DollarSign,
  ExternalLink,
  Mail,
  MapPin,
  Share2,
} from "lucide-react";
import { useEvent } from "@/hooks/useEvent";
import { Header } from "@/components/Header";
import { displayUrl, formatDate, isUpcoming } from "@/utils/formatters";

export function EventDetailPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const { event, loading, error } = useEvent(eventId ?? "");
  const [copied, setCopied] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);

  const handleShare = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback: select the URL bar
    }
  };

  const upcoming = event ? isUpcoming(event.date) : false;

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <Header onRefresh={() => {}} loading={false} />

      <main className="max-w-3xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <Link
            to=".."
            relative="path"
            className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            <ArrowLeft size={16} />
            All events
          </Link>

          <button
            onClick={() => void handleShare()}
            className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] transition-colors"
          >
            {copied ? <Check size={14} className="text-green-500" /> : <Share2 size={14} />}
            {copied ? "Copied!" : "Share"}
          </button>
        </div>

        {loading && (
          <div className="animate-pulse space-y-4">
            <div className="h-56 rounded-xl bg-[var(--color-border)]" />
            <div className="h-8 bg-[var(--color-border)] rounded w-3/4" />
            <div className="h-4 bg-[var(--color-border)] rounded w-1/2" />
            <div className="h-4 bg-[var(--color-border)] rounded w-1/3" />
            <div className="h-24 bg-[var(--color-border)] rounded" />
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-400">
            <strong>Could not load event:</strong> {error}
          </div>
        )}

        {!loading && !error && event && (
          <article className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden shadow-card">
            {event.image_url && (
              <img
                src={event.image_url}
                alt={event.event_name}
                className="w-full h-56 md:h-72 object-cover"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
            )}

            <div className="p-6 md:p-8 space-y-6">
              <div className="flex items-start justify-between gap-4">
                <h1 className="text-2xl font-bold text-[var(--color-text-primary)] leading-tight">
                  {event.event_name || "Untitled Event"}
                </h1>
                {upcoming && (
                  <span className="shrink-0 text-xs font-medium px-2.5 py-1 rounded-full bg-[var(--color-badge)] text-[var(--color-badge-text)]">
                    Upcoming
                  </span>
                )}
              </div>

              <dl className="flex flex-col gap-2.5 text-sm text-[var(--color-text-secondary)]">
                {event.date && (
                  <div className="flex items-center gap-2.5">
                    <Calendar size={15} className="shrink-0 text-[var(--color-primary)]" />
                    <dd className="font-medium">
                      {formatDate(event.date)}
                      {event.time ? ` · ${event.time}` : ""}
                    </dd>
                  </div>
                )}
                {event.venue && (
                  <div className="flex items-center gap-2.5">
                    <MapPin size={15} className="shrink-0 text-[var(--color-primary)]" />
                    <dd>{event.venue}</dd>
                  </div>
                )}
                {event.price && (
                  <div className="flex items-center gap-2.5">
                    <DollarSign size={15} className="shrink-0 text-[var(--color-primary)]" />
                    <dd>{event.price}</dd>
                  </div>
                )}
              </dl>

              {event.description && (
                <div>
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
                    About
                  </h2>
                  <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed whitespace-pre-line">
                    {event.description}
                  </p>
                </div>
              )}

              {event.links && event.links.length > 0 && (
                <div>
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
                    Links
                  </h2>
                  <div className="flex flex-col gap-1.5">
                    {event.links.map((url, i) => (
                      <a
                        key={i}
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 text-sm text-[var(--color-primary)] hover:text-[var(--color-primary-hover)] hover:underline"
                      >
                        <ExternalLink size={13} />
                        {displayUrl(url)}
                      </a>
                    ))}
                  </div>
                </div>
              )}

              <div className="border-t border-[var(--color-border)] pt-4">
                <button
                  onClick={() => setSourceOpen((v) => !v)}
                  className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
                >
                  <Mail size={13} />
                  Source email
                  {sourceOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                </button>

                {sourceOpen && (
                  <dl className="mt-3 space-y-1.5 text-xs text-[var(--color-text-muted)]">
                    {event.email_subject && (
                      <div className="flex gap-2">
                        <dt className="font-medium shrink-0">Subject</dt>
                        <dd>{event.email_subject}</dd>
                      </div>
                    )}
                    {event.email_sender && (
                      <div className="flex gap-2">
                        <dt className="font-medium shrink-0">From</dt>
                        <dd>{event.email_sender}</dd>
                      </div>
                    )}
                    {event.source_email_date && (
                      <div className="flex gap-2">
                        <dt className="font-medium shrink-0">Date</dt>
                        <dd>{event.source_email_date}</dd>
                      </div>
                    )}
                  </dl>
                )}
              </div>
            </div>
          </article>
        )}
      </main>
    </div>
  );
}
