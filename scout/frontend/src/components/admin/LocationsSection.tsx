import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { useApi } from "@/api";
import { Button, ErrorBanner, Spinner } from "@/components/ui";
import type { Location } from "@/types";

function CreateLocationForm({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const api = useApi();
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.createLocation({ name, address, timezone });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  };

  const field =
    "w-full rounded-none border-b border-[var(--color-rule)] bg-transparent py-2 text-sm text-[var(--color-text-primary)] focus:outline-none";

  return (
    <div className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <h2 className="mb-4 font-serif text-xl leading-none text-[var(--color-text-primary)]">
        New location
      </h2>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        {error && <ErrorBanner message={error} />}
        <input className={field} placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <input className={field} placeholder="Address" value={address} onChange={(e) => setAddress(e.target.value)} />
        <input className={field} placeholder="IANA timezone (e.g. America/New_York)" value={timezone} onChange={(e) => setTimezone(e.target.value)} />
        <div className="flex gap-2">
          <Button type="submit" variant="primary">Create</Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </div>
  );
}

export function LocationsSection() {
  const api = useApi();
  const [locations, setLocations] = useState<Location[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pendingDelete, setPendingDelete] = useState<Location | null>(null);
  const [confirmMerge, setConfirmMerge] = useState(false);
  // Single in-flight action key (e.g. "<location_id>:delete" or "merge").
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const isBusy = (key: string) => actionBusy === key;

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    if (!silent) setError(null);
    if (!silent) {
      setPendingDelete(null);
      setConfirmMerge(false);
    }
    try {
      const data = await api.listLocations();
      setLocations(data.locations);
      if (!silent) setSelected(new Set());
    } catch (err) {
      if (!silent) setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const toggle = (id: string) =>
    setSelected((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const runAction = async (
    key: string,
    call: () => Promise<unknown>,
    applyOptimistic?: () => void
  ) => {
    setActionBusy(key);
    setError(null);
    try {
      await call();
      applyOptimistic?.();
      void refresh(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setActionBusy(null);
    }
  };

  const confirmDelete = () => {
    if (!pendingDelete) return Promise.resolve();
    const lid = pendingDelete.location_id;
    return runAction(
      `${lid}:delete`,
      () => api.deleteLocation(lid, true),
      () => {
        setPendingDelete(null);
        setLocations((prev) => prev.filter((l) => l.location_id !== lid));
      }
    );
  };

  const mergeNames = locations
    .filter((l) => selected.has(l.location_id))
    .map((l) => l.name);

  const doMerge = () => {
    const ids = [...selected];
    if (ids.length < 2) return Promise.resolve();
    const dropped = new Set(ids.slice(1));
    return runAction(
      "merge",
      () => api.mergeLocations(ids[0], ids.slice(1)),
      () => {
        setConfirmMerge(false);
        setSelected(new Set());
        setLocations((prev) => prev.filter((l) => !dropped.has(l.location_id)));
      }
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--color-text-muted)]">
          {selected.size >= 2
            ? "First selected is the merge target."
            : "Select 2+ to merge."}
        </p>
        <div className="flex gap-2">
          {selected.size >= 2 && (
            <Button onClick={() => setConfirmMerge(true)}>Merge {selected.size}</Button>
          )}
          <Button variant="primary" onClick={() => setCreating((c) => !c)}>
            <Plus size={15} />
            New
          </Button>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      {confirmMerge && selected.size >= 2 && (
        <div className="flex flex-col gap-2 border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm text-[var(--color-text-secondary)] sm:flex-row sm:items-center sm:justify-between">
          <span>
            Merge {mergeNames.join(", ")} into &ldquo;{mergeNames[0]}&rdquo;? Other locations are
            soft-deleted.
          </span>
          <div className="flex shrink-0 gap-2">
            <Button
              variant="danger"
              disabled={isBusy("merge")}
              onClick={() => void doMerge()}
            >
              {isBusy("merge") && <Loader2 size={14} className="animate-spin" />}
              Merge
            </Button>
            <Button onClick={() => setConfirmMerge(false)}>Cancel</Button>
          </div>
        </div>
      )}

      {creating && (
        <CreateLocationForm onClose={() => setCreating(false)} onCreated={() => void refresh(true)} />
      )}

      {loading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : locations.length === 0 ? (
        <p className="py-12 text-center text-sm text-[var(--color-text-muted)]">No locations.</p>
      ) : (
        <ul className="border-t border-[var(--color-rule)]">
          {locations.map((loc) => (
            <li
              key={loc.location_id}
              className="flex flex-col gap-3 border-b border-[var(--color-border)] py-4"
            >
              <div className="flex items-center justify-between gap-3">
                <label className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={selected.has(loc.location_id)}
                    onChange={() => toggle(loc.location_id)}
                    className="h-4 w-4 shrink-0 accent-[var(--color-primary)]"
                  />
                  <span>
                    <span className="font-serif text-base text-[var(--color-text-primary)]">{loc.name}</span>
                    <span className="ml-2 text-xs text-[var(--color-text-muted)]">
                      {loc.address} · {loc.timezone}
                    </span>
                  </span>
                </label>
                <Button
                  variant="danger"
                  disabled={isBusy(`${loc.location_id}:delete`)}
                  onClick={() => setPendingDelete(loc)}
                >
                  <Trash2 size={14} />
                </Button>
              </div>

              {pendingDelete?.location_id === loc.location_id && (
                <div className="flex flex-col gap-2 border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm text-[var(--color-text-secondary)] sm:flex-row sm:items-center sm:justify-between">
                  <span>Delete &ldquo;{loc.name}&rdquo;? Associated events cascade.</span>
                  <div className="flex shrink-0 gap-2">
                    <Button
                      variant="danger"
                      disabled={isBusy(`${loc.location_id}:delete`)}
                      onClick={() => void confirmDelete()}
                    >
                      {isBusy(`${loc.location_id}:delete`) && (
                        <Loader2 size={14} className="animate-spin" />
                      )}
                      Delete
                    </Button>
                    <Button onClick={() => setPendingDelete(null)}>Cancel</Button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
