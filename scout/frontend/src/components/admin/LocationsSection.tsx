import { useCallback, useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useApi } from "@/api";
import { Button, ErrorBanner, Modal, Spinner } from "@/components/ui";
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
    "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]";

  return (
    <Modal title="New location" onClose={onClose}>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        {error && <ErrorBanner message={error} />}
        <input className={field} placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <input className={field} placeholder="Address" value={address} onChange={(e) => setAddress(e.target.value)} />
        <input className={field} placeholder="IANA timezone (e.g. America/New_York)" value={timezone} onChange={(e) => setTimezone(e.target.value)} />
        <Button type="submit" variant="primary">Create</Button>
      </form>
    </Modal>
  );
}

export function LocationsSection() {
  const api = useApi();
  const [locations, setLocations] = useState<Location[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listLocations();
      setLocations(data.locations);
      setSelected(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
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

  const remove = async (loc: Location) => {
    if (!window.confirm(`Delete "${loc.name}"? Associated events cascade.`)) return;
    try {
      await api.deleteLocation(loc.location_id, true);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const merge = async () => {
    const ids = [...selected];
    if (ids.length < 2) return;
    const target = ids[0];
    const names = locations.filter((l) => ids.includes(l.location_id)).map((l) => l.name);
    if (!window.confirm(`Merge ${names.join(", ")} into "${names[0]}"? Other locations are soft-deleted.`)) return;
    try {
      await api.mergeLocations(target, ids.slice(1));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Merge failed");
    }
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
            <Button onClick={() => void merge()}>Merge {selected.size}</Button>
          )}
          <Button variant="primary" onClick={() => setCreating(true)}>
            <Plus size={15} />
            New
          </Button>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      {loading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : locations.length === 0 ? (
        <p className="py-12 text-center text-sm text-[var(--color-text-muted)]">No locations.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {locations.map((loc) => (
            <li
              key={loc.location_id}
              className="flex items-center justify-between gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
            >
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={selected.has(loc.location_id)} onChange={() => toggle(loc.location_id)} />
                <span>
                  <span className="text-sm font-medium text-[var(--color-text-primary)]">{loc.name}</span>
                  <span className="ml-2 text-xs text-[var(--color-text-muted)]">
                    {loc.address} · {loc.timezone}
                  </span>
                </span>
              </label>
              <Button variant="danger" onClick={() => void remove(loc)}>
                <Trash2 size={14} />
              </Button>
            </li>
          ))}
        </ul>
      )}

      {creating && <CreateLocationForm onClose={() => setCreating(false)} onCreated={() => void refresh()} />}
    </div>
  );
}
