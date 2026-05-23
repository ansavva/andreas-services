import { useCallback, useEffect, useState } from "react";
import { Check, Plus, Tag, Trash2 } from "lucide-react";
import type { Category } from "@/types";
import { useAdminApi } from "@/hooks/useAdminApi";
import { useAuth } from "@/context/AuthContext";
import { SkeletonCard } from "@/components/SkeletonCard";

export function AdminCategoriesSection() {
  const api = useAdminApi();
  const { idToken } = useAuth();
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newName, setNewName] = useState("");

  const fetchCategories = useCallback(async () => {
    if (!idToken) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.listAdminCategories("all");
      setCategories(data.categories ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [api, idToken]);

  useEffect(() => {
    void fetchCategories();
  }, [fetchCategories]);

  const runAction = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await fetchCategories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const suggested = categories.filter((c) => c.status === "suggested");
  const active = categories.filter((c) => c.status === "active");

  return (
    <div className="flex flex-col gap-6">
      {error && (
        <div className="rounded-lg border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : (
        <>
          <section>
            <h3 className="mb-2 text-sm font-semibold text-[var(--color-text-primary)]">
              Suggested categories
            </h3>
            {suggested.length === 0 ? (
              <p className="text-xs text-[var(--color-text-muted)]">No suggested categories.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {suggested.map((cat) => (
                  <div
                    key={cat.slug}
                    className="flex items-center justify-between gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-[var(--color-text-primary)] truncate">
                        {cat.name}
                      </p>
                      <p className="text-xs text-[var(--color-text-muted)]">
                        {cat.slug}
                        {typeof cat.suggested_count === "number"
                          ? ` · ${cat.suggested_count} event${cat.suggested_count === 1 ? "" : "s"}`
                          : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        onClick={() => void runAction(() => api.approveCategory({ slug: cat.slug, name: cat.name }))}
                        disabled={busy}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-green-600 hover:bg-green-700 px-2.5 py-1 text-xs font-medium text-white transition-colors disabled:opacity-50"
                      >
                        <Check size={13} />
                        Approve
                      </button>
                      <button
                        onClick={() => void runAction(() => api.rejectCategory(cat.slug))}
                        disabled={busy}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-red-300 dark:border-red-900 px-2.5 py-1 text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors disabled:opacity-50"
                      >
                        <Trash2 size={13} />
                        Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold text-[var(--color-text-primary)]">
              Active categories
            </h3>
            <div className="mb-3 flex items-center gap-2">
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="New category name"
                className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-background)] text-[var(--color-text-primary)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
              />
              <button
                onClick={() =>
                  void runAction(async () => {
                    await api.approveCategory({ name: newName });
                    setNewName("");
                  })
                }
                disabled={busy || !newName.trim()}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] px-3 py-2 text-xs font-medium text-white transition-colors disabled:opacity-50"
              >
                <Plus size={14} />
                Add
              </button>
            </div>
            {active.length === 0 ? (
              <p className="text-xs text-[var(--color-text-muted)]">No active categories.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {active.map((cat) => (
                  <span
                    key={cat.slug}
                    className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] px-2.5 py-1 text-xs font-medium text-[var(--color-text-secondary)]"
                  >
                    <Tag size={12} className="text-[var(--color-text-muted)]" />
                    {cat.name}
                    <button
                      onClick={() => void runAction(() => api.rejectCategory(cat.slug))}
                      disabled={busy}
                      title="Remove category"
                      className="text-[var(--color-text-muted)] hover:text-red-500 transition-colors disabled:opacity-50"
                    >
                      <Trash2 size={12} />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
