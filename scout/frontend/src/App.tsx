import { useMemo, useState } from "react";
import { Calendar } from "lucide-react";
import { ThemeProvider } from "@/context/ThemeContext";
import { useEvents } from "@/hooks/useEvents";
import { Header } from "@/components/Header";
import { EventFilters } from "@/components/EventFilters";
import { EventCard } from "@/components/EventCard";
import { SkeletonCard } from "@/components/SkeletonCard";
import type { SortOrder } from "@/types";
import "@/index.css";

function AppContent() {
  const [upcomingOnly, setUpcomingOnly] = useState(false);
  const [sortOrder, setSortOrder] = useState<SortOrder>("date-asc");

  const { events, loading, error, refetch } = useEvents(upcomingOnly);

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
      <Header onRefresh={refetch} loading={loading} />

      <main className="max-w-6xl mx-auto px-4 py-8">
        <EventFilters
          upcomingOnly={upcomingOnly}
          setUpcomingOnly={setUpcomingOnly}
          sortOrder={sortOrder}
          setSortOrder={setSortOrder}
          total={sortedEvents.length}
        />

        {error && (
          <div className="mb-6 rounded-lg border border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-400">
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
              <EventCard key={ev.event_id} event={ev} />
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
              {upcomingOnly
                ? "No upcoming events. Try turning off the upcoming filter."
                : "No events yet. Run the email processor to populate events."}
            </p>
            {upcomingOnly && (
              <button
                onClick={() => setUpcomingOnly(false)}
                className="text-sm text-[var(--color-primary)] hover:underline"
              >
                Show all events
              </button>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  );
}
