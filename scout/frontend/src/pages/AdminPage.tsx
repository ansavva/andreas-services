import { Link, useNavigate, useSearchParams } from "react-router-dom";
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

const TABS: { key: Tab; label: string }[] = [
  { key: "review", label: "Review queue" },
  { key: "sources", label: "Sources" },
  { key: "locations", label: "Locations" },
  { key: "labels", label: "Labels" },
  { key: "notifications", label: "Notifications" },
  { key: "deleted", label: "Deleted" },
  { key: "settings", label: "Settings" },
];

// Sentinel value for the mobile dropdown: not a tab, navigates to the
// full-screen swipe-review page instead of switching the active section.
const SWIPE_REVIEW = "__swipe_review";

export function AdminPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tab: Tab = TABS.some((t) => t.key === tabParam) ? (tabParam as Tab) : "review";
  const setTab = (key: Tab) =>
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("tab", key);
        return next;
      },
      { replace: true }
    );

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <header className="sticky top-0 z-10 border-b border-[var(--color-rule)] bg-[var(--color-surface)]">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div className="flex items-baseline gap-3">
            <h1 className="font-serif text-xl leading-none text-[var(--color-text-primary)]">
              Scout
            </h1>
            <span className="eyebrow text-[var(--color-text-muted)]">Admin</span>
          </div>
          <div className="flex items-center gap-5">
            {user && (
              <span className="hidden max-w-[12rem] truncate text-xs text-[var(--color-text-muted)] md:block">
                {user}
              </span>
            )}
            <Link
              to="/"
              className="eyebrow text-[var(--color-text-secondary)] no-underline hover:text-[var(--color-text-primary)] hover:underline"
            >
              View site
            </Link>
            <button
              onClick={logout}
              className="eyebrow text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:underline"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5 py-8 sm:px-6">
        <nav className="mb-8 border-b border-[var(--color-rule)]">
          {/* Mobile: a single dropdown instead of a horizontally-scrolling tab
              strip (which clashed with the per-section sub-tabs). */}
          <div className="pb-3 sm:hidden">
            <select
              value={tab}
              onChange={(e) => {
                if (e.target.value === SWIPE_REVIEW) navigate("/admin/review-queue");
                else setTab(e.target.value as Tab);
              }}
              className="w-full rounded-none border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm uppercase tracking-[0.1em] text-[var(--color-text-primary)] focus:border-[var(--color-text-primary)] focus:outline-none"
            >
              {TABS.map(({ key, label }) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
              <option value={SWIPE_REVIEW}>Swipe review →</option>
            </select>
          </div>

          {/* Desktop: the full horizontal tab row. */}
          <div className="no-scrollbar -mb-px hidden gap-6 overflow-x-auto sm:flex">
            {TABS.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`shrink-0 whitespace-nowrap border-b-2 px-1 py-3 text-[11px] font-medium uppercase tracking-[0.14em] transition-colors ${
                  tab === key
                    ? "border-[var(--color-primary)] text-[var(--color-text-primary)]"
                    : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
                }`}
              >
                {label}
              </button>
            ))}
            <Link
              to="/admin/review-queue"
              className="shrink-0 whitespace-nowrap border-b-2 border-transparent px-1 py-3 text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--color-text-muted)] no-underline transition-colors hover:text-[var(--color-text-primary)]"
            >
              Swipe review
            </Link>
          </div>
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
