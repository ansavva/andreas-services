import { useCallback, useEffect, useState } from "react";
import { CalendarX, Search } from "lucide-react";
import { useApi } from "@/api";
import { Header } from "@/components/Header";
import { EventCard } from "@/components/EventCard";
import { Button, Chip, ErrorBanner, Spinner } from "@/components/ui";
import type { Facets, PublicEvent, PublicFilters } from "@/types";

const EMPTY_FILTERS: PublicFilters = { event_labels: [], location_labels: [] };

export function PublicListPage() {
  const api = useApi();
  const [facets, setFacets] = useState<Facets | null>(null);
  const [filters, setFilters] = useState<PublicFilters>(EMPTY_FILTERS);
  const [searchInput, setSearchInput] = useState("");
  const [events, setEvents] = useState<PublicEvent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <Header />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <form onSubmit={submitSearch} className="mb-4 flex gap-2">
          <div className="relative flex-1">
            <Search
              size={16}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]"
            />
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search events…"
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] py-2 pl-9 pr-3 text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
            />
          </div>
          <Button type="submit" variant="primary">
            Search
          </Button>
        </form>

        {facets && (
          <div className="mb-6 flex flex-col gap-3">
            {facets.locations.length > 0 && (
              <select
                aria-label="Location"
                value={filters.location_id ?? ""}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, location_id: e.target.value || undefined }))
                }
                className="w-full max-w-xs cursor-pointer rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm text-[var(--color-text-secondary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
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
              <div className="flex flex-wrap gap-1.5">
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
              <div className="flex flex-wrap gap-1.5">
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
                className="self-start text-xs text-[var(--color-primary)] hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
        )}

        {error && <ErrorBanner message={error} />}

        {loading ? (
          <div className="flex justify-center py-24">
            <Spinner />
          </div>
        ) : events.length > 0 ? (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {events.map((ev) => (
                <EventCard key={ev.event_id} event={ev} />
              ))}
            </div>
            {cursor && (
              <div className="mt-8 flex justify-center">
                <Button onClick={() => void loadMore()}>Load more</Button>
              </div>
            )}
          </>
        ) : (
          <div className="flex flex-col items-center gap-3 py-24 text-center">
            <CalendarX size={44} className="text-[var(--color-text-muted)]" />
            <p className="text-sm text-[var(--color-text-muted)]">
              {hasFilters ? "No events match your filters." : "No events yet."}
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
