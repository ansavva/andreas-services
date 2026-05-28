import { useCallback, useEffect, useState } from "react";
import { Inbox, Loader2, Play, Plus, Trash2 } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "@/api";
import { Badge, Button, ErrorBanner, Spinner, SubTabs } from "@/components/ui";
import { formatDateTime } from "@/utils/formatters";
import type { ArtifactDescriptor, Source, SourceRun, SourceType } from "@/types";

const SOURCE_TABS = [
  { key: "active", label: "Active" },
  { key: "archived", label: "Archived" },
];
const POLL_MS = 3000;
// Stop waiting on a triggered run that never reports back (processor max ~5 min).
const PENDING_TIMEOUT_MS = 6 * 60 * 1000;

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

// Stored logs are JSON (transcript) or raw text; pretty-print JSON when we can.
function prettyLog(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

function RunsPanel({ sourceId }: { sourceId: string }) {
  const api = useApi();
  const [runs, setRuns] = useState<SourceRun[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openLog, setOpenLog] = useState<string | null>(null);
  const [logContent, setLogContent] = useState<Record<string, string>>({});
  const [logLoading, setLogLoading] = useState<string | null>(null);
  const [logError, setLogError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api
      .listRuns(sourceId)
      .then((data) => {
        if (!active) return;
        setRuns(data.runs);
        setCursor(data.next_cursor);
      })
      .catch((err) =>
        active && setError(err instanceof Error ? err.message : "Failed to load runs")
      );
    return () => {
      active = false;
    };
  }, [api, sourceId]);

  const loadMoreRuns = async () => {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const data = await api.listRuns(sourceId, cursor);
      setRuns((prev) => [...(prev ?? []), ...data.runs]);
      setCursor(data.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load more");
    } finally {
      setLoadingMore(false);
    }
  };

  // Fetch the artifact in byte-range chunks until the server reports EOF,
  // accumulating the text so the inline <pre> renders the full file even when
  // it's much larger than the per-call response cap.
  const toggleLog = async (run: SourceRun, descriptor: ArtifactDescriptor) => {
    const key = `${run.run_id}:${descriptor.kind}:${descriptor.index ?? ""}`;
    if (openLog === key) {
      setOpenLog(null);
      return;
    }
    setOpenLog(key);
    setLogError(null);
    if (logContent[key] !== undefined) return;
    setLogLoading(key);
    try {
      let assembled = "";
      let offset = 0;
      // Safety cap so a misconfigured server can't loop forever.
      for (let i = 0; i < 200; i++) {
        const chunk = await api.fetchArtifactChunk(descriptor.url, offset);
        assembled += chunk.content;
        if (chunk.next_offset === null) break;
        offset = chunk.next_offset;
      }
      setLogContent((c) => ({ ...c, [key]: assembled }));
    } catch (err) {
      setLogError(err instanceof Error ? err.message : "Failed to load log");
    } finally {
      setLogLoading(null);
    }
  };

  return (
    <div className="border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <h3 className="eyebrow mb-3 text-[var(--color-text-muted)]">Run history</h3>
      {error ? (
        <ErrorBanner message={error} />
      ) : !runs ? (
        <div className="flex justify-center py-6">
          <Spinner />
        </div>
      ) : runs.length === 0 ? (
        <p className="py-2 text-sm text-[var(--color-text-muted)]">No runs yet.</p>
      ) : (
        <ul className="flex flex-col">
          {runs.map((r) => {
            const links = r.link_outcomes ?? [];
            const okLinks = links.filter((l) => l.ok).length;
            const count = r.events_count ?? 0;
            const summary = r.extracted_summary;
            const logs = r.artifacts ?? [];
            const openKey = openLog && openLog.startsWith(`${r.run_id}:`) ? openLog : null;
            return (
              <li
                key={r.run_id}
                className="flex flex-col gap-1.5 border-b border-[var(--color-border)] py-3 text-sm last:border-b-0"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge value={r.status} />
                  <span className="text-[11px] uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
                    {r.trigger}
                  </span>
                  <span className="text-xs text-[var(--color-text-muted)]">
                    {formatDateTime(r.started_at)}
                    {r.finished_at ? ` → ${formatDateTime(r.finished_at)}` : ""}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[var(--color-text-secondary)]">
                  <span>
                    {count} event{count === 1 ? "" : "s"} extracted
                  </span>
                  {summary?.skipped ? <span>{summary.skipped} duplicate(s) skipped</span> : null}
                  {summary?.pages ? (
                    <span>
                      {summary.pages} page{summary.pages === 1 ? "" : "s"} read
                    </span>
                  ) : null}
                  {links.length > 0 && (
                    <span>
                      {okLinks}/{links.length} link{links.length === 1 ? "" : "s"} fetched
                    </span>
                  )}
                  {r.error_reason && (
                    <span className="text-[var(--color-text-primary)]">{r.error_reason}</span>
                  )}
                </div>

                {logs.length > 0 && (
                  <div className="-mx-1 flex flex-wrap gap-x-1">
                    {logs.map((log) => {
                      const key = `${r.run_id}:${log.kind}:${log.index ?? ""}`;
                      return (
                        <Button
                          key={key}
                          variant="ghost"
                          onClick={() => void toggleLog(r, log)}
                        >
                          {openLog === key ? `Hide ${log.label.toLowerCase()}` : log.label}
                        </Button>
                      );
                    })}
                  </div>
                )}

                {openKey && (
                  <div className="mt-1">
                    {logLoading === openKey ? (
                      <div className="flex justify-center py-4">
                        <Spinner />
                      </div>
                    ) : logError ? (
                      <ErrorBanner message={logError} />
                    ) : (
                      <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words border border-[var(--color-border)] bg-[var(--color-background)] p-3 text-xs text-[var(--color-text-secondary)]">
                        {prettyLog(logContent[openKey] ?? "")}
                      </pre>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {cursor && (
        <div className="mt-3">
          <Button onClick={() => void loadMoreRuns()} disabled={loadingMore}>
            {loadingMore ? "Loading…" : "Load more runs"}
          </Button>
        </div>
      )}
    </div>
  );
}

export function SourcesSection() {
  const api = useApi();
  const [searchParams, setSearchParams] = useSearchParams();
  const archived = searchParams.get("archived") === "true";
  const setArchived = (val: boolean) =>
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (val) next.set("archived", "true");
        else next.delete("archived");
        return next;
      },
      { replace: true }
    );

  const [sources, setSources] = useState<Source[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [creating, setCreating] = useState(false);
  const [openRuns, setOpenRuns] = useState<string | null>(null);
  // Running-source ids as reported by the lightweight /admin/sources/running
  // endpoint, plus optimistic ids for sources we just clicked Run on.
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set());
  const [pending, setPending] = useState<Record<string, { since: string; at: number }>>({});
  const [pendingDelete, setPendingDelete] = useState<
    { source: Source; events: number; subevents: number; runs: number } | null
  >(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listSources(archived);
      setSources(data.sources);
      setCursor(data.next_cursor);
      const serverRunning = new Set(
        data.sources.filter((s) => s.running).map((s) => s.source_id)
      );
      setRunningIds(serverRunning);
      // Drop pending entries the server already reports finished (last_run_at
      // moved) or that timed out.
      setPending((prev) => {
        const next = { ...prev };
        const now = Date.now();
        const byId = new Map(data.sources.map((s) => [s.source_id, s]));
        for (const id of Object.keys(next)) {
          const s = byId.get(id);
          if (s && !s.running && (s.last_run_at ?? "") !== next[id].since) delete next[id];
          else if (now - next[id].at > PENDING_TIMEOUT_MS) delete next[id];
        }
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [api, archived]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const loadMore = async () => {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const data = await api.listSources(archived, cursor);
      setSources((prev) => [...prev, ...data.sources]);
      setCursor(data.next_cursor);
      setRunningIds((prev) => {
        const next = new Set(prev);
        for (const s of data.sources) {
          if (s.running) next.add(s.source_id);
        }
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load more");
    } finally {
      setLoadingMore(false);
    }
  };

  // Lightweight running-spinner poll: hits the dedicated /admin/sources/running
  // endpoint so the spinner state updates without re-paginating the list.
  const busy = runningIds.size > 0 || Object.keys(pending).length > 0;
  useEffect(() => {
    if (!busy) return;
    const id = window.setInterval(() => {
      void api
        .sourcesRunning()
        .then((data) => {
          setRunningIds(new Set(data.running));
          // Once a pending source either appears as no-longer-running OR is
          // older than the timeout, drop it.
          setPending((prev) => {
            const next = { ...prev };
            const now = Date.now();
            for (const sid of Object.keys(next)) {
              if (!data.running.includes(sid) || now - next[sid].at > PENDING_TIMEOUT_MS) {
                delete next[sid];
              }
            }
            return next;
          });
        })
        .catch(() => {
          /* transient — keep polling */
        });
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [busy, api]);

  // When polling clears the spinner, refresh the visible page once so any
  // last_run_status/at fields catch up. Triggered by busy transitioning to false.
  const wasBusy = useBusyTransition(busy);
  useEffect(() => {
    if (wasBusy && !busy) void reload();
  }, [wasBusy, busy, reload]);

  const isRunning = (s: Source) => runningIds.has(s.source_id) || s.source_id in pending;

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    }
  };

  const run = async (s: Source) => {
    setError(null);
    setPending((p) => ({ ...p, [s.source_id]: { since: s.last_run_at ?? "", at: Date.now() } }));
    try {
      await api.runSource(s.source_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
      setPending((p) => {
        const next = { ...p };
        delete next[s.source_id];
        return next;
      });
    }
  };

  const scanInbox = async () => {
    setScanning(true);
    setError(null);
    try {
      await api.scanInbox();
      setNotice(
        'Scanning the Gmail "Events" label. New sender domains will appear as active email sources shortly.'
      );
      window.setTimeout(() => void reload(), 5000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
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
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SubTabs
          tabs={SOURCE_TABS}
          value={archived ? "archived" : "active"}
          onChange={(k) => setArchived(k === "archived")}
        />
        <div className="flex gap-2">
          <Button onClick={() => void scanInbox()} disabled={scanning} title="Scan the Gmail Events label for new email sources">
            {scanning ? <Loader2 size={15} className="animate-spin" /> : <Inbox size={15} />}
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
        <CreateSourceForm onClose={() => setCreating(false)} onCreated={() => void reload()} />
      )}

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : sources.length === 0 ? (
        <p className="py-12 text-center text-sm text-[var(--color-text-muted)]">No sources.</p>
      ) : (
        <ul className="border-t border-[var(--color-rule)]">
          {sources.map((s) => {
            const running = isRunning(s);
            return (
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
                    <Button onClick={() => void run(s)} disabled={running} title="Run now">
                      {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                      {running ? "Running" : "Run"}
                    </Button>
                    <Button
                      onClick={() => setOpenRuns((o) => (o === s.source_id ? null : s.source_id))}
                    >
                      {openRuns === s.source_id ? "Hide runs" : "Runs"}
                    </Button>
                    <Button onClick={() => void act(() => api.archiveSource(s.source_id, !s.archived))}>
                      {s.archived ? "Unarchive" : "Archive"}
                    </Button>
                    <Button variant="danger" onClick={() => void startDelete(s)} title="Delete">
                      <Trash2 size={14} />
                    </Button>
                  </div>
                </div>

                {openRuns === s.source_id && <RunsPanel sourceId={s.source_id} />}

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
            );
          })}
        </ul>
      )}

      {cursor && (
        <Button onClick={() => void loadMore()} disabled={loadingMore}>
          {loadingMore ? "Loading…" : "Load more"}
        </Button>
      )}
    </div>
  );
}

// Returns the previous value of `busy` so an effect can detect the transition
// from "polling" back to "idle" and refresh the visible page once.
function useBusyTransition(busy: boolean): boolean {
  const [prev, setPrev] = useState(busy);
  useEffect(() => {
    setPrev(busy);
  }, [busy]);
  return prev;
}
