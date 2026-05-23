import { useMemo } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Calendar } from "lucide-react";
import { useEvents } from "@/hooks/useEvents";
import { useCategories } from "@/hooks/useCategories";
import { Header } from "@/components/Header";
import { EventFilters } from "@/components/EventFilters";
import { EventCard } from "@/components/EventCard";
import { SkeletonCard } from "@/components/SkeletonCard";
import type { SortOrder } from "@/types";

export function EventsListPage() {
  const { region } = useParams<{ region: string }>();
  const [searchParams, setSearchParams] = useSearchParams();

  const upcomingOnly = searchParams.get("upcoming") === "true";
  const sortOrder = (searchParams.get("sort") as SortOrder | null) ?? "date-asc";
  const category = searchParams.get("category");

  function setUpcomingOnly(value: boolean) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set("upcoming", "true");
        else next.delete("upcoming");
        return next;
      },
      { replace: true }
    );
  }

  function setSortOrder(value: SortOrder) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value === "date-asc") next.delete("sort");
        else next.set("sort", value);
        return next;
      },
      { replace: true }
    );
  }

  function setCategory(slug: string | null) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (slug) next.set("category", slug);
        else next.delete("category");
        return next;
      },
      { replace: true }
    );
  }

  const { events, loading, error, refetch } = useEvents({
    region,
    category: category ?? undefined,
    upcoming: upcomingOnly,
  });
  const { categories } = useCategories();

  const sortedEvents = useMemo(() => {
    const copy = [...events];
    if (sortOrder === "date-desc") {
      copy.sort((a, b) => {
        if (!a.date && !b.date) return 0;
        if (!a.date) return 1;
        if (!b.date) return -1;
        return b.date.localeCompare(a.date);
      });
    } else if (sortOrder === "name-asc") {
      copy.sort((a, b) => (a.event_name ?? "").localeCompare(b.event_name ?? ""));
    }
    return copy;
  }, [events, sortOrder]);

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <Header onRefresh={refetch} loading={loading} showRegionSelector />

      <main className="max-w-6xl mx-auto px-4 py-8">
        <EventFilters
          upcomingOnly={upcomingOnly}
          setUpcomingOnly={setUpcomingOnly}
          sortOrder={sortOrder}
          setSortOrder={setSortOrder}
          total={sortedEvents.length}
          categories={categories}
          selectedCategory={category}
          setCategory={setCategory}
        />

        {error && (
          <div className="mb-6 rounded-lg border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-400">
            <strong>Could not load events:</strong> {error}
          </div>
        )}

        {loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {!loading && !error && sortedEvents.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {sortedEvents.map((ev) => (
              <EventCard key={ev.event_id} event={ev} categories={categories} />
            ))}
          </div>
        )}

        {!loading && !error && sortedEvents.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 text-center gap-4">
            <Calendar size={48} className="text-[var(--color-text-muted)]" />
            <h2 className="text-lg font-medium text-[var(--color-text-secondary)]">
              No events found
            </h2>
            <p className="text-sm text-[var(--color-text-muted)] max-w-sm">
              {upcomingOnly || category
                ? "No events match the current filters. Try clearing them."
                : "No events yet. Run the email processor to populate events."}
            </p>
            {(upcomingOnly || category) && (
              <button
                onClick={() => {
                  setUpcomingOnly(false);
                  setCategory(null);
                }}
                className="text-sm text-[var(--color-primary)] hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
