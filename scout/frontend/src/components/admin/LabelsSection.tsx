import { useCallback, useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useApi } from "@/api";
import { Button, ErrorBanner, Spinner } from "@/components/ui";
import type { Label, LabelTaxonomy } from "@/types";

const TAXONOMIES: { key: LabelTaxonomy; label: string }[] = [
  { key: "event", label: "Event labels" },
  { key: "location", label: "Location labels" },
  { key: "source", label: "Source labels" },
];

export function LabelsSection() {
  const api = useApi();
  const [taxonomy, setTaxonomy] = useState<LabelTaxonomy>("event");
  const [labels, setLabels] = useState<Label[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listLabels(taxonomy);
      setLabels(data.labels);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [api, taxonomy]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await api.createLabel(taxonomy, name.trim());
      setName("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  };

  const remove = async (id: string) => {
    try {
      await api.deleteLabel(taxonomy, id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
        {TAXONOMIES.map((t) => (
          <button
            key={t.key}
            onClick={() => setTaxonomy(t.key)}
            className={`shrink-0 whitespace-nowrap rounded-none px-3 py-2 text-[11px] font-medium uppercase tracking-[0.12em] transition-colors ${
              taxonomy === t.key
                ? "bg-[var(--color-primary)] text-white"
                : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <form onSubmit={(e) => void create(e)} className="flex gap-3">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New label name"
          className="flex-1 rounded-none border-b border-[var(--color-rule)] bg-transparent py-2 text-sm text-[var(--color-text-primary)] focus:outline-none"
        />
        <Button type="submit" variant="primary">
          <Plus size={15} />
          Add
        </Button>
      </form>

      {error && <ErrorBanner message={error} />}

      {loading ? (
        <div className="flex justify-center py-12"><Spinner /></div>
      ) : labels.length === 0 ? (
        <p className="py-8 text-center text-sm text-[var(--color-text-muted)]">No labels.</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {labels.map((l) => (
            <li
              key={l.label_id}
              className="inline-flex items-center gap-2 rounded-none border border-[var(--color-border)] py-1 pl-3 pr-1.5 text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-primary)]"
            >
              {l.name}
              <button
                onClick={() => void remove(l.label_id)}
                className="rounded-none p-1 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
                title="Delete"
              >
                <Trash2 size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
