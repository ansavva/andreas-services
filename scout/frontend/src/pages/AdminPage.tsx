import { useContext, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Bell,
  CalendarCheck,
  LogOut,
  MapPin,
  Moon,
  Rss,
  Settings as SettingsIcon,
  Sun,
  Tag,
  Trash2,
} from "lucide-react";
import { ThemeContext } from "@/context/ThemeContext";
import { useAuth } from "@/context/AuthContext";
import { ReviewSection } from "@/components/admin/ReviewSection";
import { SourcesSection } from "@/components/admin/SourcesSection";
import { LocationsSection } from "@/components/admin/LocationsSection";
import { LabelsSection } from "@/components/admin/LabelsSection";
import { SettingsSection } from "@/components/admin/SettingsSection";
import { NotificationsSection } from "@/components/admin/NotificationsSection";
import { DeletedSection } from "@/components/admin/DeletedSection";

type Tab =
  | "review"
  | "sources"
  | "locations"
  | "labels"
  | "notifications"
  | "deleted"
  | "settings";

const TABS: { key: Tab; label: string; icon: typeof CalendarCheck }[] = [
  { key: "review", label: "Review queue", icon: CalendarCheck },
  { key: "sources", label: "Sources", icon: Rss },
  { key: "locations", label: "Locations", icon: MapPin },
  { key: "labels", label: "Labels", icon: Tag },
  { key: "notifications", label: "Notifications", icon: Bell },
  { key: "deleted", label: "Deleted", icon: Trash2 },
  { key: "settings", label: "Settings", icon: SettingsIcon },
];

export function AdminPage() {
  const { theme, toggleTheme } = useContext(ThemeContext);
  const { user, logout } = useAuth();
  const [tab, setTab] = useState<Tab>("review");

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <header className="sticky top-0 z-10 theme-transition border-b border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
          <div>
            <h1 className="text-xl font-bold leading-tight text-[var(--color-text-primary)]">
              Scout admin
            </h1>
            {user && <p className="hidden text-xs text-[var(--color-text-muted)] sm:block">{user}</p>}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={toggleTheme}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              className="rounded-lg p-2 text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)]"
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <Link
              to="/"
              title="Back to events"
              className="rounded-lg p-2 text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)]"
            >
              <ArrowLeft size={18} />
            </Link>
            <button
              onClick={logout}
              title="Sign out"
              className="inline-flex items-center gap-1.5 rounded-lg p-2 text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)]"
            >
              <LogOut size={18} />
              <span className="hidden text-sm sm:inline">Sign out</span>
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8">
        <nav className="mb-6 flex flex-wrap gap-2 border-b border-[var(--color-border)]">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`-mb-px inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                tab === key
                  ? "border-[var(--color-primary)] text-[var(--color-primary)]"
                  : "border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
              }`}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </nav>

        {tab === "review" && <ReviewSection />}
        {tab === "sources" && <SourcesSection />}
        {tab === "locations" && <LocationsSection />}
        {tab === "labels" && <LabelsSection />}
        {tab === "notifications" && <NotificationsSection />}
        {tab === "deleted" && <DeletedSection />}
        {tab === "settings" && <SettingsSection />}
      </main>
    </div>
  );
}
