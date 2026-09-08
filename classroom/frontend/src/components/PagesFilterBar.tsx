import { Chip, Input, InputGroup } from "@ansavva/design-system";

export type PageFilter = "all" | "published" | "drafts";

const FILTERS: ReadonlyArray<{ value: PageFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "published", label: "Published" },
  { value: "drafts", label: "Drafts" },
];

function SearchIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      aria-hidden
    >
      <circle cx="7" cy="7" r="4.5" />
      <path d="m10.4 10.4 3.1 3.1" />
    </svg>
  );
}

/**
 * Find a page, the way the teaching-resource sites this is modelled on do it:
 * a pill-shaped search field with the magnifier inside it, and pill filter
 * chips under it.
 *
 * **Chips rather than tabs, deliberately.** "Published" and "Drafts" are two
 * filters of one list, not two places — a tab whose whole content is a preset
 * filter of the tab beside it is a saved search dressed up as navigation. Chips
 * say "narrowing" where tabs would say "elsewhere", and they combine with the
 * search box instead of competing with it.
 *
 * `pressed` is the package's own selected state on Chip, so the active filter
 * picks up the brand green with no colour written here.
 */
export function PagesFilterBar({
  query,
  onQueryChange,
  filter,
  onFilterChange,
  counts,
}: {
  query: string;
  onQueryChange: (next: string) => void;
  filter: PageFilter;
  onFilterChange: (next: PageFilter) => void;
  counts: Record<PageFilter, number>;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3">
      <InputGroup.Root className="rounded-pill">
        <InputGroup.Text>
          <SearchIcon />
        </InputGroup.Text>
        <Input
          type="search"
          value={query}
          onValueChange={onQueryChange}
          placeholder="Search your pages…"
          aria-label="Search your pages"
        />
      </InputGroup.Root>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map(({ value, label }) => (
          <Chip
            key={value}
            pressed={filter === value}
            onClick={() => onFilterChange(value)}
            // A chip that filters is a toggle, and a screen reader should hear
            // which one is on rather than infer it from the fill.
            aria-pressed={filter === value} className="rounded-pill">
            {label} ({counts[value]})
          </Chip>
        ))}
      </div>
    </div>
  );
}
