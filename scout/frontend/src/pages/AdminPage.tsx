import { useContext, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, CalendarCheck, LogOut, Mail, Moon, Sun, Tag, Users } from "lucide-react";
import { ThemeContext } from "@/context/ThemeContext";
import { useAuth } from "@/context/AuthContext";
import { AdminEventsSection } from "@/components/admin/AdminEventsSection";
import { AdminSendersSection } from "@/components/admin/AdminSendersSection";
import { AdminCategoriesSection } from "@/components/admin/AdminCategoriesSection";
import { AdminEmailsSection } from "@/components/admin/AdminEmailsSection";

type Tab = "events" | "senders" | "categories" | "emails";

const TABS: { key: Tab; label: string; icon: typeof CalendarCheck }[] = [
  { key: "events", label: "Approval queue", icon: CalendarCheck },
  { key: "senders", label: "Senders", icon: Users },
  { key: "categories", label: "Categories", icon: Tag },
  { key: "emails", label: "Emails", icon: Mail },
];

export function AdminPage() {
  const { theme, toggleTheme } = useContext(ThemeContext);
  const { user, logout } = useAuth();
  const [tab, setTab] = useState<Tab>("events");

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <header className="sticky top-0 z-10 theme-transition bg-[var(--color-surface)] border-b border-[var(--color-border)] shadow-sm">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-[var(--color-text-primary)] leading-tight">
              Scout admin
            </h1>
            {user && (
              <p className="text-xs text-[var(--color-text-muted)] hidden sm:block">{user}</p>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={toggleTheme}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              className="p-2 rounded-lg text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] transition-colors"
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>

            <Link
              to="/"
              title="Back to events"
              className="p-2 rounded-lg text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] transition-colors"
            >
              <ArrowLeft size={18} />
            </Link>

            <button
              onClick={logout}
              title="Sign out"
              className="inline-flex items-center gap-1.5 p-2 rounded-lg text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] transition-colors"
            >
              <LogOut size={18} />
              <span className="hidden sm:inline text-sm">Sign out</span>
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        <nav className="mb-6 flex flex-wrap gap-2 border-b border-[var(--color-border)]">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
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

        {tab === "events" && <AdminEventsSection />}
        {tab === "senders" && <AdminSendersSection />}
        {tab === "categories" && <AdminCategoriesSection />}
        {tab === "emails" && <AdminEmailsSection />}
      </main>
    </div>
  );
}
