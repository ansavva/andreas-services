import { useContext } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, MapPin, Moon, RefreshCw, Settings, Sun } from "lucide-react";
import { ThemeContext } from "@/context/ThemeContext";
import { useRegions } from "@/hooks/useRegions";

interface HeaderProps {
  onRefresh: () => void;
  loading: boolean;
  /** Show the region selector (public browse pages only). */
  showRegionSelector?: boolean;
}

function RegionSelector() {
  const { regions } = useRegions();
  const { region } = useParams<{ region: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  if (regions.length === 0) return null;

  const handleChange = (slug: string) => {
    navigate({ pathname: `/${slug}`, search: location.search });
  };

  return (
    <label className="relative inline-flex items-center">
      <MapPin
        size={15}
        className="pointer-events-none absolute left-2.5 text-[var(--color-text-muted)]"
      />
      <select
        aria-label="Region"
        value={region ?? ""}
        onChange={(e) => handleChange(e.target.value)}
        className="appearance-none text-sm rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] pl-8 pr-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)] cursor-pointer"
      >
        {!region && (
          <option value="" disabled>
            Select region
          </option>
        )}
        {regions.map((r) => (
          <option key={r.slug} value={r.slug}>
            {r.name} ({r.count})
          </option>
        ))}
      </select>
    </label>
  );
}

export function Header({ onRefresh, loading, showRegionSelector = false }: HeaderProps) {
  const { theme, toggleTheme } = useContext(ThemeContext);
  const location = useLocation();
  const { pathname } = location;
  const isAdmin = pathname === "/admin";
  const fromSearch = (location.state as { fromSearch?: string } | null)?.fromSearch ?? "";

  return (
    <header className="sticky top-0 z-10 theme-transition bg-[var(--color-surface)] border-b border-[var(--color-border)] shadow-sm">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-[var(--color-text-primary)] leading-tight">
            Scout
          </h1>
          <p className="text-xs text-[var(--color-text-muted)] hidden sm:block">
            Scout events from your inbox
          </p>
        </div>

        <div className="flex items-center gap-2">
          {showRegionSelector && <RegionSelector />}

          <button
            onClick={onRefresh}
            disabled={loading}
            title="Refresh"
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

          {isAdmin ? (
            <Link
              to={{ pathname: "/", search: fromSearch }}
              title="Back to events"
              className="p-2 rounded-lg text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] transition-colors"
            >
              <ArrowLeft size={18} />
            </Link>
          ) : (
            <Link
              to="/admin"
              state={{ fromSearch: location.search }}
              title="Admin"
              className="p-2 rounded-lg text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] transition-colors"
            >
              <Settings size={18} />
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
