import { useMemo, useRef, useState } from "react";
import type { Label } from "@/types";

/**
 * Inline editor for an entity's event-labels: shows each selected label as a
 * removable chip and an "add" combobox that picks an existing label or creates
 * a new one. Writes the full selected id list back via `onChange`.
 */
export function LabelEditor({
  selectedIds,
  labels,
  onChange,
  onCreate,
}: {
  selectedIds: string[];
  labels: Label[];
  onChange: (ids: string[]) => void;
  onCreate: (name: string) => Promise<Label>;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const blurTimer = useRef<number | undefined>(undefined);

  const byId = useMemo(() => new Map(labels.map((l) => [l.label_id, l])), [labels]);
  const selected = selectedIds.map((id) => byId.get(id)).filter((l): l is Label => !!l);

  const available = useMemo(() => {
    const q = query.trim().toLowerCase();
    return labels.filter(
      (l) => !selectedIds.includes(l.label_id) && l.name.toLowerCase().includes(q)
    );
  }, [labels, selectedIds, query]);

  const exactMatch = labels.some(
    (l) => l.name.toLowerCase() === query.trim().toLowerCase()
  );

  const close = () => {
    blurTimer.current = window.setTimeout(() => setOpen(false), 120);
  };
  const cancelClose = () => window.clearTimeout(blurTimer.current);

  const add = (id: string) => {
    onChange([...selectedIds, id]);
    setQuery("");
    setOpen(false);
  };
  const remove = (id: string) => onChange(selectedIds.filter((x) => x !== id));

  async function handleCreate() {
    const name = query.trim();
    if (!name) return;
    setCreating(true);
    try {
      const lbl = await onCreate(name);
      onChange([...selectedIds, lbl.label_id]);
      setQuery("");
      setOpen(false);
    } finally {
      setCreating(false);
    }
  }

  const chip =
    "inline-flex items-center gap-1 rounded-none border px-2.5 py-1 text-[11px] uppercase tracking-[0.12em] border-[var(--color-border)] text-[var(--color-text-secondary)]";

  return (
    <div className="flex flex-wrap items-center gap-2">
      {selected.map((l) => (
        <span key={l.label_id} className={chip}>
          {l.name}
          <button
            type="button"
            onClick={() => remove(l.label_id)}
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
            title="Remove label"
          >
            ×
          </button>
        </span>
      ))}
      <div className="relative">
        <input
          type="text"
          value={query}
          placeholder="+ label"
          onFocus={() => setOpen(true)}
          onChange={(e) => setQuery(e.target.value)}
          onBlur={close}
          className="w-24 border-b border-dashed border-[var(--color-border)] bg-transparent py-1 text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-secondary)] outline-none focus:border-[var(--color-text-primary)]"
        />
        {open && (
          <ul
            className="absolute z-10 mt-1 max-h-56 w-48 overflow-auto border border-[var(--color-border)] bg-[var(--color-background)] shadow-sm"
            onMouseDown={cancelClose}
          >
            {available.map((l) => (
              <li key={l.label_id}>
                <button
                  type="button"
                  onClick={() => add(l.label_id)}
                  className="block w-full px-3 py-2 text-left text-sm text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]"
                >
                  {l.name}
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
            {available.length === 0 && !query.trim() && (
              <li className="px-3 py-2 text-sm text-[var(--color-text-muted)]">
                No more labels
              </li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
