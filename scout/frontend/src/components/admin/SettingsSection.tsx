import { useCallback, useEffect, useState } from "react";
import { useApi } from "@/api";
import { Button, ErrorBanner, Spinner } from "@/components/ui";
import type { Settings } from "@/types";

const LABELS: Record<string, string> = {
  system_timezone: "System timezone",
  fallback_timezone: "Fallback timezone",
  past_grace_hours: "Past-event grace (hours)",
  health_zero_event_runs: "Zero-event runs to flag stale",
  health_overdue_hours: "Overdue threshold (hours)",
  link_follow_cap: "Link-follow cap",
  default_agent_model: "Default agent model",
  default_agent_budget_tokens: "Default agent token budget",
  default_agent_budget_seconds: "Default agent runtime budget (s)",
};

export function SettingsSection() {
  const api = useApi();
  const [settings, setSettings] = useState<Settings>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setSettings(await api.getSettings());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const next = await api.updateSettings(settings);
      setSettings(next);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="flex justify-center py-16"><Spinner /></div>;

  return (
    <form onSubmit={(e) => void save(e)} className="flex max-w-lg flex-col gap-3">
      {error && <ErrorBanner message={error} />}
      {Object.keys(LABELS).map((key) => (
        <label key={key} className="flex flex-col gap-1.5">
          <span className="eyebrow text-[var(--color-text-muted)]">{LABELS[key]}</span>
          <input
            value={String(settings[key] ?? "")}
            onChange={(e) => setSettings((s) => ({ ...s, [key]: e.target.value }))}
            className="rounded-none border-b border-[var(--color-rule)] bg-transparent py-2 text-sm text-[var(--color-text-primary)] focus:outline-none"
          />
        </label>
      ))}
      <div className="flex items-center gap-3">
        <Button type="submit" variant="primary" disabled={saving}>
          {saving ? "Saving…" : "Save settings"}
        </Button>
        {saved && <span className="eyebrow text-[var(--color-text-primary)]">Saved</span>}
      </div>
    </form>
  );
}
