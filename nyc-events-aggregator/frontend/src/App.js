import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  Calendar,
  Clock,
  DollarSign,
  ExternalLink,
  MapPin,
  Moon,
  RefreshCw,
  Sun,
} from "lucide-react";
import { displayUrl, formatDate, isUpcoming, truncate } from "./lib/utils";
import "./index.css";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const API_BASE =
  process.env.REACT_APP_API_URL ||
  "https://your-api-id.execute-api.us-east-1.amazonaws.com/prod";

// ---------------------------------------------------------------------------
// Theme context
// ---------------------------------------------------------------------------
const ThemeContext = createContext({ theme: "light", toggleTheme: () => {} });

function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    const stored = localStorage.getItem("nyc-events-theme");
    if (stored) return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    localStorage.setItem("nyc-events-theme", theme);
  }, [theme]);

  const toggleTheme = useCallback(
    () => setTheme((t) => (t === "dark" ? "light" : "dark")),
    []
  );

  const value = useMemo(() => ({ theme, toggleTheme }), [theme, toggleTheme]);
  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------
function Header({ onRefresh, loading }) {
  const { theme, toggleTheme } = useContext(ThemeContext);

  return (
    <header className="sticky top-0 z-10 theme-transition bg-surface border-b border-[var(--color-border)] shadow-sm">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-[var(--color-text-primary)] leading-tight">
            NYC Events
          </h1>
          <p className="text-xs text-[var(--color-text-muted)] hidden sm:block">
            Curated from your inbox
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onRefresh}
            disabled={loading}
            title="Refresh events"
            className="p-2 rounded-lg text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] transition-colors disabled:opacity-40"
          >
            <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
          </button>

          <button
            onClick={toggleTheme}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            className="p-2 rounded-lg text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] transition-colors"
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// EventFilters
// ---------------------------------------------------------------------------
function EventFilters({ upcomingOnly, setUpcomingOnly, sortOrder, setSortOrder, total }) {
  return (
    <div className="flex flex-wrap items-center gap-3 mb-6">
      <span className="text-sm text-[var(--color-text-muted)]">
        {total} event{total !== 1 ? "s" : ""}
      </span>

      <div className="flex-1" />

      {/* Upcoming toggle */}
      <label className="flex items-center gap-2 cursor-pointer select-none text-sm text-[var(--color-text-secondary)]">
        <span>Upcoming only</span>
        <button
          role="switch"
          aria-checked={upcomingOnly}
          onClick={() => setUpcomingOnly((v) => !v)}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] ${
            upcomingOnly
              ? "bg-[var(--color-primary)]"
              : "bg-[var(--color-border)]"
          }`}
        >
          <span
            className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
              upcomingOnly ? "translate-x-[18px]" : "translate-x-[2px]"
            }`}
          />
        </button>
      </label>

      {/* Sort selector */}
      <select
        value={sortOrder}
        onChange={(e) => setSortOrder(e.target.value)}
        className="text-sm rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] px-2 py-1 focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)] cursor-pointer"
      >
        <option value="date-asc">Date ↑</option>
        <option value="date-desc">Date ↓</option>
        <option value="name-asc">Name A–Z</option>
      </select>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EventCard
// ---------------------------------------------------------------------------
function EventCard({ event }) {
  const upcoming = isUpcoming(event.date);
  const [expanded, setExpanded] = useState(false);
  const description = event.description || "";
  const isLong = description.length > 160;
  const displayDesc = expanded ? description : truncate(description, 160);

  return (
    <article className="theme-transition flex flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-card hover:shadow-card-hover transition-shadow p-5 gap-3">
      {/* Header row */}
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

      {/* Metadata rows */}
      <dl className="flex flex-col gap-1.5 text-sm text-[var(--color-text-secondary)]">
        {event.date && (
          <div className="flex items-center gap-2">
            <Calendar size={14} className="shrink-0 text-[var(--color-text-muted)]" />
            <dd>{formatDate(event.date)}{event.time ? ` · ${event.time}` : ""}</dd>
          </div>
        )}
        {!event.date && event.time && (
          <div className="flex items-center gap-2">
            <Clock size={14} className="shrink-0 text-[var(--color-text-muted)]" />
            <dd>{event.time}</dd>
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

      {/* Description */}
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

      {/* Links */}
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

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------
function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 flex flex-col gap-3">
      <div className="h-4 bg-[var(--color-border)] rounded w-3/4" />
      <div className="h-3 bg-[var(--color-border)] rounded w-1/2" />
      <div className="h-3 bg-[var(--color-border)] rounded w-2/3" />
      <div className="h-12 bg-[var(--color-border)] rounded" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main App
// ---------------------------------------------------------------------------
function AppContent() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [upcomingOnly, setUpcomingOnly] = useState(false);
  const [sortOrder, setSortOrder] = useState("date-asc");

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = upcomingOnly
        ? `${API_BASE}/events?upcoming=true`
        : `${API_BASE}/events`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const data = await res.json();
      setEvents(data.events || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [upcomingOnly]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  // Client-side sort (server already returns date-asc; we re-sort for other options)
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
      copy.sort((a, b) =>
        (a.event_name || "").localeCompare(b.event_name || "")
      );
    }
    // date-asc is the server default; keep as-is
    return copy;
  }, [events, sortOrder]);

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <Header onRefresh={fetchEvents} loading={loading} />

      <main className="max-w-6xl mx-auto px-4 py-8">
        <EventFilters
          upcomingOnly={upcomingOnly}
          setUpcomingOnly={setUpcomingOnly}
          sortOrder={sortOrder}
          setSortOrder={setSortOrder}
          total={sortedEvents.length}
        />

        {/* Error state */}
        {error && (
          <div className="mb-6 rounded-lg border border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-400">
            <strong>Could not load events:</strong> {error}
          </div>
        )}

        {/* Loading skeletons */}
        {loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {/* Events grid */}
        {!loading && !error && sortedEvents.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {sortedEvents.map((ev) => (
              <EventCard key={ev.event_id} event={ev} />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && sortedEvents.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 text-center gap-4">
            <Calendar size={48} className="text-[var(--color-text-muted)]" />
            <h2 className="text-lg font-medium text-[var(--color-text-secondary)]">
              No events found
            </h2>
            <p className="text-sm text-[var(--color-text-muted)] max-w-sm">
              {upcomingOnly
                ? "No upcoming events were found. Try turning off the upcoming filter."
                : "No events have been imported yet. Run the email processor to populate events."}
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
