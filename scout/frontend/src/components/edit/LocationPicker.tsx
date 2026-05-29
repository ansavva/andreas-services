import { useMemo, useRef, useState } from "react";
import type { Location } from "@/types";

/**
 * Filterable location combobox for inline editing. Lists existing locations,
 * lets the admin pick one, clear it (inherit / none), or create a new one by
 * name. Writes a `location_id` (or null). Styled to read like the muted
 * eyebrow meta line it replaces, so the editing affordance is subtle.
 */
export function LocationPicker({
  value,
  locations,
  onChange,
  onCreate,
  placeholder = "Add a location",
}: {
  value: string | null;
  locations: Location[];
  onChange: (id: string | null) => void;
  onCreate: (name: string) => Promise<Location>;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const blurTimer = useRef<number | undefined>(undefined);

  const selected = useMemo(
    () => locations.find((l) => l.location_id === value) ?? null,
    [locations, value]
  );

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return locations;
    return locations.filter(
      (l) =>
        l.name.toLowerCase().includes(q) || l.address.toLowerCase().includes(q)
    );
  }, [locations, query]);

  const exactMatch = locations.some(
    (l) => l.name.toLowerCase() === query.trim().toLowerCase()
  );

  const close = () => {
    blurTimer.current = window.setTimeout(() => setOpen(false), 120);
  };
  const cancelClose = () => window.clearTimeout(blurTimer.current);

  async function handleCreate() {
    const name = query.trim();
    if (!name) return;
    setCreating(true);
    try {
      const loc = await onCreate(name);
      onChange(loc.location_id);
      setQuery("");
      setOpen(false);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="relative inline-block w-full max-w-sm">
      <input
        type="text"
        value={open ? query : selected ? `${selected.name}${selected.address ? `, ${selected.address}` : ""}` : ""}
        placeholder={placeholder}
        onFocus={() => {
          setOpen(true);
          setQuery("");
        }}
        onChange={(e) => setQuery(e.target.value)}
        onBlur={close}
        className="eyebrow w-full border-b border-dashed border-[var(--color-border)] bg-transparent py-1 text-[var(--color-text-secondary)] outline-none focus:border-[var(--color-text-primary)]"
      />
      {value && !open && (
        <button
          type="button"
          onClick={() => onChange(null)}
          className="absolute right-0 top-1 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
          title="Clear location"
        >
          ×
        </button>
      )}
      {open && (
        <ul
          className="absolute z-10 mt-1 max-h-56 w-full overflow-auto border border-[var(--color-border)] bg-[var(--color-background)] shadow-sm"
          onMouseDown={cancelClose}
        >
          {matches.map((l) => (
            <li key={l.location_id}>
              <button
                type="button"
                onClick={() => {
                  onChange(l.location_id);
                  setOpen(false);
                }}
                className="block w-full px-3 py-2 text-left text-sm text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]"
              >
                {l.name}
                {l.address && (
                  <span className="text-[var(--color-text-muted)]"> · {l.address}</span>
                )}
              </button>
            </li>
          ))}
          {query.trim() && !exactMatch && (
            <li>
              <button
                type="button"
                disabled={creating}
                onClick={handleCreate}
                className="block w-full px-3 py-2 text-left text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] disabled:opacity-50"
              >
                + Create “{query.trim()}”
              </button>
            </li>
          )}
          {matches.length === 0 && !query.trim() && (
            <li className="px-3 py-2 text-sm text-[var(--color-text-muted)]">
              No locations yet
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
