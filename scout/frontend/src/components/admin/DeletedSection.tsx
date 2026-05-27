import { useCallback, useEffect, useState } from "react";
import { Undo2 } from "lucide-react";
import { useApi } from "@/api";
import { Button, ErrorBanner, Spinner } from "@/components/ui";
import type { DeletedItem } from "@/types";

const TYPES = [
  { key: "source", label: "Sources" },
  { key: "event", label: "Events" },
  { key: "location", label: "Locations" },
  { key: "event_label", label: "Event labels" },
  { key: "location_label", label: "Location labels" },
  { key: "source_label", label: "Source labels" },
];

function describe(item: DeletedItem): string {
  return item.title || item.name || item.identity || item.SK;
}

export function DeletedSection() {
  const api = useApi();
  const [type, setType] = useState("source");
  const [items, setItems] = useState<DeletedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listDeleted(type);
      setItems(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [api, type]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const restore = async (item: DeletedItem) => {
    try {
      await api.restore(item.PK, item.SK);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Restore failed");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        {TYPES.map((t) => (
          <button
            key={t.key}
            onClick={() => setType(t.key)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              type === t.key
                ? "bg-[var(--color-primary)] text-white"
                : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <ErrorBanner message={error} />}

      {loading ? (
        <div className="flex justify-center py-12"><Spinner /></div>
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-sm text-[var(--color-text-muted)]">Nothing deleted.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li
              key={`${item.PK}#${item.SK}`}
              className="flex items-center justify-between gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
            >
              <span className="text-sm text-[var(--color-text-primary)]">{describe(item)}</span>
              <Button onClick={() => void restore(item)}>
                <Undo2 size={14} />
                Restore
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
