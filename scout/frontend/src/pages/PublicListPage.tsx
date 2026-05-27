import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { useApi } from "@/api";
import { Header } from "@/components/Header";
import { EventCard } from "@/components/EventCard";
import { Chip, ErrorBanner, Spinner } from "@/components/ui";
import { formatDate, truncate } from "@/utils/formatters";
import type { Facets, PublicEvent, PublicFilters } from "@/types";

const EMPTY_FILTERS: PublicFilters = { event_labels: [], location_labels: [] };

const ISSUE_LABEL = new Date().toLocaleDateString("en-US", {
  month: "long",
  year: "numeric",
});

function leadImage(event: PublicEvent): string | null {
  return event.images.find((i) => i.url)?.url ?? null;
}

function LeadEvent({ event }: { event: PublicEvent }) {
  const image = leadImage(event);
  const kicker = [...event.event_labels, ...event.location_labels][0]?.name;
  const href = `/events/${event.event_id}`;

  return (
    <Link to={href} className="group grid gap-6 no-underline lg:grid-cols-2 lg:gap-12">
      <div className="aspect-[4/3] w-full overflow-hidden bg-[var(--color-surface-hover)] lg:aspect-[5/4]">
        {image && (
          <img
            src={image}
            alt={event.title}
            className="h-full w-full object-cover grayscale transition-[filter] duration-700 ease-out group-hover:grayscale-0"
          />
        )}
      </div>
      <div className="flex flex-col justify-center">
        <span className="eyebrow text-[var(--color-text-muted)]">
          Featured{kicker ? ` · ${kicker}` : ""}
        </span>
        <h2 className="mt-3 font-serif text-hero font-light text-[var(--color-text-primary)] underline-offset-[6px] group-hover:underline">
          {event.title || "Untitled event"}
        </h2>
        <div className="eyebrow mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 text-[var(--color-text-secondary)]">
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
          <p className="mt-5 max-w-prose text-base leading-relaxed text-[var(--color-text-secondary)]">
            {truncate(event.description, 240)}
          </p>
        )}
      </div>
    </Link>
  );
}

export function PublicListPage() {
  const api = useApi();
  const [facets, setFacets] = useState<Facets | null>(null);
  const [filters, setFilters] = useState<PublicFilters>(EMPTY_FILTERS);
  const [searchInput, setSearchInput] = useState("");
  const [events, setEvents] = useState<PublicEvent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    api
      .facets()
      .then(setFacets)
      .catch(() => setFacets(null));
  }, [api]);

  const load = useCallback(
    async (next: PublicFilters) => {
      setLoading(true);
      setError(null);
      try {
        const page = await api.feed(next);
        setEvents(page.events);
        setCursor(page.next_cursor);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load events");
      } finally {
        setLoading(false);
      }
    },
    [api]
  );

  useEffect(() => {
    void load(filters);
  }, [load, filters]);

  const loadMore = async () => {
    if (!cursor) return;
    try {
      const page = await api.feed(filters, cursor);
      setEvents((prev) => [...prev, ...page.events]);
      setCursor(page.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load more");
    }
  };

  const toggle = (key: "event_labels" | "location_labels", id: string) =>
    setFilters((f) => {
      const set = new Set(f[key]);
      set.has(id) ? set.delete(id) : set.add(id);
      return { ...f, [key]: [...set] };
    });

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setFilters((f) => ({ ...f, q: searchInput.trim() || undefined }));
  };

  const hasFilters =
    !!filters.location_id ||
    filters.event_labels.length > 0 ||
    filters.location_labels.length > 0 ||
    !!filters.q;

  const [lead, ...rest] = events;

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <Header />

      {/* Editorial masthead / hero */}
      <section className="border-b border-[var(--color-rule)]">
        <div className="mx-auto max-w-6xl px-5 py-12 sm:px-6 sm:py-16 lg:py-24">
          <p className="eyebrow text-[var(--color-text-muted)]">The Edit · {ISSUE_LABEL}</p>
          <h1 className="mt-5 max-w-4xl font-serif text-display font-light text-[var(--color-text-primary)]">
            Things worth leaving the house for.
          </h1>
          <p className="mt-6 max-w-xl text-base leading-relaxed text-[var(--color-text-secondary)] sm:text-lg">
            A calendar gathered from across the city and read by hand — no noise, no
            algorithms, just the few things we think deserve your evening.
          </p>
        </div>
      </section>

      <main className="mx-auto max-w-6xl px-5 py-10 sm:px-6 sm:py-14">
        {/* Search + filters */}
        <div className="mb-12 border-b border-[var(--color-border)] pb-8">
          <form
            onSubmit={submitSearch}
            className="flex items-center gap-3 border-b border-[var(--color-rule)] pb-3"
          >
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search the edit…"
              className="w-full bg-transparent text-base text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none"
            />
            <button
              type="submit"
              aria-label="Search"
              className="shrink-0 p-1 text-[var(--color-text-primary)]"
            >
              <Search size={18} />
            </button>
          </form>

          {facets && (
            <>
              <button
                type="button"
                onClick={() => setShowFilters((v) => !v)}
                className="eyebrow mt-5 flex items-center gap-2 text-[var(--color-text-secondary)] sm:hidden"
              >
                Filters
                <span className="text-base leading-none">{showFilters ? "−" : "+"}</span>
              </button>

              <div
                className={`${showFilters ? "flex" : "hidden"} mt-5 flex-col gap-5 sm:flex`}
              >
                {facets.locations.length > 0 && (
                  <select
                    aria-label="Location"
                    value={filters.location_id ?? ""}
                    onChange={(e) =>
                      setFilters((f) => ({ ...f, location_id: e.target.value || undefined }))
                    }
                    className="w-full max-w-xs cursor-pointer border-b border-[var(--color-border)] bg-transparent py-2 pr-6 text-xs uppercase tracking-[0.12em] text-[var(--color-text-secondary)] focus:outline-none"
                  >
                    <option value="">All locations</option>
                    {facets.locations.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name}
                      </option>
                    ))}
                  </select>
                )}
                {facets.event_labels.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {facets.event_labels.map((l) => (
                      <Chip
                        key={l.id}
                        label={l.name}
                        active={filters.event_labels.includes(l.id)}
                        onClick={() => toggle("event_labels", l.id)}
                      />
                    ))}
                  </div>
                )}
                {facets.location_labels.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {facets.location_labels.map((l) => (
                      <Chip
                        key={l.id}
                        label={l.name}
                        active={filters.location_labels.includes(l.id)}
                        onClick={() => toggle("location_labels", l.id)}
                      />
                    ))}
                  </div>
                )}
                {hasFilters && (
                  <button
                    onClick={() => {
                      setSearchInput("");
                      setFilters(EMPTY_FILTERS);
                    }}
                    className="eyebrow self-start text-[var(--color-text-muted)] underline-offset-4 hover:text-[var(--color-text-primary)] hover:underline"
                  >
                    Clear filters
                  </button>
                )}
              </div>
            </>
          )}
        </div>

        {error && <ErrorBanner message={error} />}

        {loading ? (
          <div className="flex justify-center py-24">
            <Spinner />
          </div>
        ) : events.length > 0 ? (
          <>
            <LeadEvent event={lead} />

            {rest.length > 0 && (
              <div className="mt-16 border-t border-[var(--color-rule)] pt-14">
                <div className="grid grid-cols-1 gap-x-8 gap-y-14 sm:grid-cols-2 lg:grid-cols-3">
                  {rest.map((ev) => (
                    <EventCard key={ev.event_id} event={ev} />
                  ))}
                </div>
              </div>
            )}

            {cursor && (
              <div className="mt-16 flex justify-center">
                <button
                  onClick={() => void loadMore()}
                  className="eyebrow text-[var(--color-text-primary)] underline-offset-4 hover:underline"
                >
                  Load more ↓
                </button>
              </div>
            )}
          </>
        ) : (
          <div className="flex flex-col items-center gap-3 py-24 text-center">
            <p className="font-serif text-2xl text-[var(--color-text-primary)]">
              {hasFilters ? "Nothing matches — yet." : "The edit is being written."}
            </p>
            <p className="text-sm text-[var(--color-text-muted)]">
              {hasFilters
                ? "Try clearing a filter or two."
                : "Check back soon for the next selection."}
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
