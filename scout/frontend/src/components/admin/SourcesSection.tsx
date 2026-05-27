import { useCallback, useEffect, useState } from "react";
import { Inbox, Play, Plus, Trash2 } from "lucide-react";
import { useApi } from "@/api";
import { Badge, Button, ErrorBanner, Spinner } from "@/components/ui";
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
    "w-full rounded-none border-b border-[var(--color-rule)] bg-transparent py-2 text-sm text-[var(--color-text-primary)] focus:outline-none";

  return (
    <div className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <h2 className="mb-4 font-serif text-xl leading-none text-[var(--color-text-primary)]">
        New source
      </h2>
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
        <div className="flex gap-2">
          <Button type="submit" variant="primary">
            Create
          </Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </div>
  );
}

export function SourcesSection() {
  const api = useApi();
  const [archived, setArchived] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<
    { source: Source; events: number; subevents: number; runs: number } | null
  >(null);

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

  const scanInbox = async () => {
    try {
      await api.scanInbox();
      setError(null);
      setNotice(
        'Scanning the Gmail "Events" label. New sender domains will appear as active email sources shortly.'
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    }
  };

  const startDelete = async (s: Source) => {
    try {
      const preview = await api.deleteSourcePreview(s.source_id);
      setPendingDelete({ source: s, ...preview });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await api.deleteSource(pendingDelete.source.source_id, true);
      setPendingDelete(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2">
          <button
            onClick={() => setArchived(false)}
            className={`rounded-none px-3 py-2 text-[11px] font-medium uppercase tracking-[0.12em] transition-colors ${
              !archived ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            Active
          </button>
          <button
            onClick={() => setArchived(true)}
            className={`rounded-none px-3 py-2 text-[11px] font-medium uppercase tracking-[0.12em] transition-colors ${
              archived ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            Archived
          </button>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => void scanInbox()} title="Scan the Gmail Events label for new email sources">
            <Inbox size={15} />
            Scan inbox
          </Button>
          <Button variant="primary" onClick={() => setCreating((c) => !c)}>
            <Plus size={15} />
            New source
          </Button>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
      {notice && (
        <div className="flex items-start justify-between gap-3 border-l-2 border-[var(--color-rule)] bg-[var(--color-surface-hover)] px-4 py-3 text-sm text-[var(--color-text-primary)]">
          <span>{notice}</span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            className="shrink-0 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
          >
            Dismiss
          </button>
        </div>
      )}

      {creating && (
        <CreateSourceForm onClose={() => setCreating(false)} onCreated={() => void refresh()} />
      )}

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : sources.length === 0 ? (
        <p className="py-12 text-center text-sm text-[var(--color-text-muted)]">No sources.</p>
      ) : (
        <ul className="border-t border-[var(--color-rule)]">
          {sources.map((s) => (
            <li
              key={s.source_id}
              className="flex flex-col gap-3 border-b border-[var(--color-border)] py-4"
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="font-serif text-base text-[var(--color-text-primary)]">{s.name}</div>
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
                  <Button variant="danger" onClick={() => void startDelete(s)} title="Delete">
                    <Trash2 size={14} />
                  </Button>
                </div>
              </div>

              {pendingDelete?.source.source_id === s.source_id && (
                <div className="flex flex-col gap-2 border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm text-[var(--color-text-secondary)] sm:flex-row sm:items-center sm:justify-between">
                  <span>
                    Delete &ldquo;{s.name}&rdquo;? Cascades {pendingDelete.events} event(s),{" "}
                    {pendingDelete.subevents} sub-event(s) and soft-deletes {pendingDelete.runs} run(s).
                  </span>
                  <div className="flex shrink-0 gap-2">
                    <Button variant="danger" onClick={() => void confirmDelete()}>
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
