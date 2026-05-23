import type { Category } from "@/types";

interface CategoryChipsProps {
  /** Category slugs assigned to the event. */
  slugs: string[];
  /** Active categories from useCategories(); used to map slug -> name and filter. */
  categories: Category[];
}

/**
 * Renders small chips only for slugs that correspond to an active category.
 * Unknown / suggested slugs are silently ignored.
 */
export function CategoryChips({ slugs, categories }: CategoryChipsProps) {
  if (!slugs || slugs.length === 0 || categories.length === 0) return null;

  const nameBySlug = new Map(categories.map((c) => [c.slug, c.name]));
  const known = slugs.filter((s) => nameBySlug.has(s));
  if (known.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {known.map((slug) => (
        <span
          key={slug}
          className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-[var(--color-badge)] text-[var(--color-badge-text)]"
        >
          {nameBySlug.get(slug)}
        </span>
      ))}
    </div>
  );
}
