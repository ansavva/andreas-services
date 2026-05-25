import { useContext } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowLeft, Moon, Settings, Sun } from "lucide-react";
import { ThemeContext } from "@/context/ThemeContext";

export function Header() {
  const { theme, toggleTheme } = useContext(ThemeContext);
  const { pathname } = useLocation();
  const isAdmin = pathname.startsWith("/admin");

  return (
    <header className="sticky top-0 z-10 theme-transition border-b border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <Link to="/" className="no-underline">
          <h1 className="text-xl font-bold leading-tight text-[var(--color-text-primary)]">
            Scout
          </h1>
          <p className="hidden text-xs text-[var(--color-text-muted)] sm:block">
            Events, scouted for you
          </p>
        </Link>

        <div className="flex items-center gap-2">
          <button
            onClick={toggleTheme}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            className="rounded-lg p-2 text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)]"
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>

          {isAdmin ? (
            <Link
              to="/"
              title="Back to events"
              className="rounded-lg p-2 text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)]"
            >
              <ArrowLeft size={18} />
            </Link>
          ) : (
            <Link
              to="/admin"
              title="Admin"
              className="rounded-lg p-2 text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)]"
            >
              <Settings size={18} />
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
