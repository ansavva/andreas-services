import { useCallback, useEffect, useState } from "react";
import { Play, Plus, Trash2 } from "lucide-react";
import { useApi } from "@/api";
import { Badge, Button, ErrorBanner, Modal, Spinner } from "@/components/ui";
import type { Source, SourceType } from "@/types";

function CreateSourceForm({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const api = useApi();
  const [type, setType] = useState<SourceType>("webpage");
  const [identity, setIdentity] = useState("");
  const [name, setName] = useState("");
  const [preset, setPreset] = useState("daily");
  const [mode, setMode] = useState("scheduled");
  const [followLinks, setFollowLinks] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const config =
      type === "email"
        ? { check_frequency: preset }
        : { mode, schedule_preset: preset };
    try {
      await api.createSource({ type, identity, name: name || undefined, config, follow_links: followLinks });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create");
    }
  };

  const field =
    "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]";

  return (
    <Modal title="New source" onClose={onClose}>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        {error && <ErrorBanner message={error} />}
        <label className="flex flex-col gap-1 text-sm text-[var(--color-text-secondary)]">
          Type
          <select value={type} onChange={(e) => setType(e.target.value as SourceType)} className={field}>
            <option value="webpage">Webpage</option>
            <option value="email">Email</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-[var(--color-text-secondary)]">
          {type === "email" ? "Sender domain" : "Root URL"}
          <input value={identity} onChange={(e) => setIdentity(e.target.value)} required className={field} />
        </label>
        <label className="flex flex-col gap-1 text-sm text-[var(--color-text-secondary)]">
          Name (optional)
          <input value={name} onChange={(e) => setName(e.target.value)} className={field} />
        </label>
        {type === "webpage" && (
          <label className="flex flex-col gap-1 text-sm text-[var(--color-text-secondary)]">
            Mode
            <select value={mode} onChange={(e) => setMode(e.target.value)} className={field}>
              <option value="scheduled">Scheduled</option>
              <option value="one-off">One-off</option>
            </select>
          </label>
        )}
        {(type === "email" || mode === "scheduled") && (
          <label className="flex flex-col gap-1 text-sm text-[var(--color-text-secondary)]">
            Frequency
            <select value={preset} onChange={(e) => setPreset(e.target.value)} className={field}>
              <option value="hourly">Hourly</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
            </select>
          </label>
        )}
        <label className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
          <input type="checkbox" checked={followLinks} onChange={(e) => setFollowLinks(e.target.checked)} />
          Follow same-domain links (one level)
        </label>
        <Button type="submit" variant="primary">
          Create
        </Button>
      </form>
    </Modal>
  );
}

export function SourcesSection() {
  const api = useApi();
  const [archived, setArchived] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listSources(archived);
      setSources(data.sources);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [api, archived]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    }
  };

  const remove = async (s: Source) => {
    try {
      const preview = await api.deleteSourcePreview(s.source_id);
      const msg = `Delete "${s.name}"? This cascades ${preview.events} event(s), ${preview.subevents} sub-event(s) and soft-deletes ${preview.runs} run(s).`;
      if (window.confirm(msg)) {
        await api.deleteSource(s.source_id, true);
        await refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <button
            onClick={() => setArchived(false)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              !archived ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text-secondary)]"
            }`}
          >
            Active
          </button>
          <button
            onClick={() => setArchived(true)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              archived ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text-secondary)]"
            }`}
          >
            Archived
          </button>
        </div>
        <Button variant="primary" onClick={() => setCreating(true)}>
          <Plus size={15} />
          New source
        </Button>
      </div>

      {error && <ErrorBanner message={error} />}

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : sources.length === 0 ? (
        <p className="py-12 text-center text-sm text-[var(--color-text-muted)]">No sources.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {sources.map((s) => (
            <li
              key={s.source_id}
              className="flex flex-col gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <div className="text-sm font-medium text-[var(--color-text-primary)]">{s.name}</div>
                <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-muted)]">
                  <span>{s.type}</span>
                  <span className="truncate">{s.identity}</span>
                  <Badge value={s.status} />
                  {s.last_run_status && <Badge value={s.last_run_status} />}
                  {s.follow_links && <span>follows links</span>}
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Button onClick={() => void act(() => api.runSource(s.source_id))} title="Run now">
                  <Play size={14} />
                  Run
                </Button>
                <Button onClick={() => void act(() => api.archiveSource(s.source_id, !s.archived))}>
                  {s.archived ? "Unarchive" : "Archive"}
                </Button>
                <Button variant="danger" onClick={() => void remove(s)} title="Delete">
                  <Trash2 size={14} />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {creating && <CreateSourceForm onClose={() => setCreating(false)} onCreated={() => void refresh()} />}
    </div>
  );
}
