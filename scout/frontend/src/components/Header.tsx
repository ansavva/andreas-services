import { useContext } from "react";
import { Moon, RefreshCw, Sun } from "lucide-react";
import { ThemeContext } from "@/context/ThemeContext";

interface HeaderProps {
  onRefresh: () => void;
  loading: boolean;
}

export function Header({ onRefresh, loading }: HeaderProps) {
  const { theme, toggleTheme } = useContext(ThemeContext);

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
