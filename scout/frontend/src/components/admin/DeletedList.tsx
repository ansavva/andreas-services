import { useCallback, useEffect, useState } from "react";
import { Loader2, Undo2 } from "lucide-react";
import { useApi } from "@/api";
import { Button, ErrorBanner, Spinner } from "@/components/ui";
import type { DeletedItem } from "@/types";

function describe(item: DeletedItem): string {
  return item.title || item.name || item.identity || item.SK;
}

/**
 * Soft-deleted items of a single entity type, with per-item restore. Rendered
 * inside each admin section's own "Deleted" sub-tab (replacing the former
 * global Deleted tab) so deleted records live alongside the section they
 * belong to.
 */
export function DeletedList({ entityType }: { entityType: string }) {
  const api = useApi();
  const [items, setItems] = useState<DeletedItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const data = await api.listDeleted(entityType);
      setItems(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }, [api, entityType]);

  useEffect(() => {
    setItems(null);
    void refresh();
  }, [refresh]);

  const restore = async (item: DeletedItem) => {
    const key = `${item.PK}#${item.SK}`;
    setBusy(key);
    setError(null);
    try {
      await api.restore(item.PK, item.SK);
      setItems((prev) => (prev ?? []).filter((i) => `${i.PK}#${i.SK}` !== key));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Restore failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {error && <ErrorBanner message={error} />}

      {!items ? (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-sm text-[var(--color-text-muted)]">Nothing deleted.</p>
      ) : (
        <ul className="border-t border-[var(--color-rule)]">
          {items.map((item) => {
            const key = `${item.PK}#${item.SK}`;
            return (
              <li
                key={key}
                className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] py-4"
              >
                <span className="text-sm text-[var(--color-text-primary)]">{describe(item)}</span>
                <Button disabled={busy === key} onClick={() => void restore(item)}>
                  {busy === key ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Undo2 size={14} />
                  )}
                  Restore
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
