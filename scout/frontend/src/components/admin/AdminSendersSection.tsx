import { useCallback, useEffect, useState } from "react";
import { Save, UserCheck } from "lucide-react";
import type { Sender } from "@/types";
import { useAdminApi } from "@/hooks/useAdminApi";
import { useAuth } from "@/context/AuthContext";
import { SkeletonCard } from "@/components/SkeletonCard";

interface SenderRowProps {
  sender: Sender;
  onSaved: () => void;
}

function SenderRow({ sender, onSaved }: SenderRowProps) {
  const api = useAdminApi();
  const [regions, setRegions] = useState((sender.regions ?? []).join(", "));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const list = regions
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await api.classifySender(sender.sender_key, list);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium text-[var(--color-text-primary)] truncate">
            {sender.display_sender || sender.sender_key}
          </p>
          <p className="text-xs text-[var(--color-text-muted)] truncate">{sender.sender_key}</p>
        </div>
        <span className="shrink-0 text-xs font-medium px-2 py-0.5 rounded-full bg-[var(--color-badge)] text-[var(--color-badge-text)]">
          {sender.status}
        </span>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <label className="flex-1 flex flex-col gap-1 text-xs font-medium text-[var(--color-text-secondary)]">
          Region slugs (comma-separated)
          <input
            value={regions}
            onChange={(e) => setRegions(e.target.value)}
            placeholder="e.g. london, bristol"
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-background)] text-[var(--color-text-primary)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
          />
        </label>
        <button
          onClick={() => void handleSave()}
          disabled={saving}
          className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] px-3 py-2 text-xs font-medium text-white transition-colors disabled:opacity-50"
        >
          <Save size={14} />
          {saving ? "Saving…" : "Save"}
        </button>
      </div>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}

export function AdminSendersSection() {
  const api = useAdminApi();
  const { idToken } = useAuth();
  const [senders, setSenders] = useState<Sender[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSenders = useCallback(async () => {
    if (!idToken) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.listSenders("pending");
      setSenders(data.senders ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [api, idToken]);

  useEffect(() => {
    void fetchSenders();
  }, [fetchSenders]);

  return (
    <div>
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Pending senders</h3>
        <p className="text-xs text-[var(--color-text-muted)]">
          Map each sender to one or more region slugs. Saving re-tags the sender&apos;s events.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {!loading && !error && senders.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center gap-3">
          <UserCheck size={40} className="text-[var(--color-text-muted)]" />
          <p className="text-sm text-[var(--color-text-muted)]">No pending senders.</p>
        </div>
      )}

      {!loading && !error && senders.length > 0 && (
        <div className="flex flex-col gap-3">
          {senders.map((sender) => (
            <SenderRow key={sender.sender_key} sender={sender} onSaved={fetchSenders} />
          ))}
        </div>
      )}
    </div>
  );
}
