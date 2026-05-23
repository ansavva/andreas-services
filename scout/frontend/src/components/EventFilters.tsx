import type { Category, SortOrder } from "@/types";

interface EventFiltersProps {
  upcomingOnly: boolean;
  setUpcomingOnly: (value: boolean) => void;
  sortOrder: SortOrder;
  setSortOrder: (value: SortOrder) => void;
  total: number;
  categories: Category[];
  selectedCategory: string | null;
  setCategory: (slug: string | null) => void;
}

export function EventFilters({
  upcomingOnly,
  setUpcomingOnly,
  sortOrder,
  setSortOrder,
  total,
  categories,
  selectedCategory,
  setCategory,
}: EventFiltersProps) {
  return (
    <div className="mb-6 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-[var(--color-text-muted)]">
          {total} event{total !== 1 ? "s" : ""}
        </span>

        <div className="flex-1" />

        <label className="flex items-center gap-2 cursor-pointer select-none text-sm text-[var(--color-text-secondary)]">
          <span>Upcoming only</span>
          <button
            role="switch"
            aria-checked={upcomingOnly}
            onClick={() => setUpcomingOnly(!upcomingOnly)}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] ${
              upcomingOnly ? "bg-[var(--color-primary)]" : "bg-[var(--color-border)]"
            }`}
          >
            <span
              className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                upcomingOnly ? "translate-x-[18px]" : "translate-x-[2px]"
              }`}
            />
          </button>
        </label>

        <select
          value={sortOrder}
          onChange={(e) => setSortOrder(e.target.value as SortOrder)}
          className="text-sm rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] px-2 py-1 focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)] cursor-pointer"
        >
          <option value="date-asc">Date ↑</option>
          <option value="date-desc">Date ↓</option>
          <option value="name-asc">Name A–Z</option>
        </select>
      </div>

      {categories.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setCategory(null)}
            className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
              selectedCategory === null
                ? "bg-[var(--color-primary)] text-white border-[var(--color-primary)]"
                : "border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]"
            }`}
          >
            All
          </button>
          {categories.map((cat) => {
            const active = selectedCategory === cat.slug;
            return (
              <button
                key={cat.slug}
                onClick={() => setCategory(active ? null : cat.slug)}
                className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
                  active
                    ? "bg-[var(--color-primary)] text-white border-[var(--color-primary)]"
                    : "border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]"
                }`}
              >
                {cat.name}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
