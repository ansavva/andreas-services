import { useState } from "react";
import { X } from "lucide-react";
import type { Event } from "@/types";
import type { EventEditFields } from "@/hooks/useAdminApi";

interface EventEditModalProps {
  event: Event;
  onClose: () => void;
  onSave: (fields: EventEditFields) => Promise<void>;
}

function joinList(list: string[] | undefined): string {
  return (list ?? []).join(", ");
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function EventEditModal({ event, onClose, onSave }: EventEditModalProps) {
  const [form, setForm] = useState({
    event_name: event.event_name ?? "",
    date: event.date ?? "",
    time: event.time ?? "",
    venue: event.venue ?? "",
    price: event.price ?? "",
    description: event.description ?? "",
    links: joinList(event.links),
    categories: joinList(event.categories),
    regions: joinList(event.regions),
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (key: keyof typeof form, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await onSave({
        event_name: form.event_name,
        date: form.date,
        time: form.time,
        venue: form.venue,
        price: form.price,
        description: form.description,
        links: splitList(form.links),
        categories: splitList(form.categories),
        regions: splitList(form.regions),
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  };

  const inputClass =
    "rounded-md border border-[var(--color-border)] bg-[var(--color-background)] text-[var(--color-text-primary)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-card">
        <div className="sticky top-0 flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-3">
          <h2 className="text-base font-semibold text-[var(--color-text-primary)]">Edit event</h2>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-3 p-5">
          <label className="flex flex-col gap-1 text-xs font-medium text-[var(--color-text-secondary)]">
            Name
            <input
              className={inputClass}
              value={form.event_name}
              onChange={(e) => update("event_name", e.target.value)}
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1 text-xs font-medium text-[var(--color-text-secondary)]">
              Date
              <input
                className={inputClass}
                placeholder="YYYY-MM-DD"
                value={form.date}
                onChange={(e) => update("date", e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-[var(--color-text-secondary)]">
              Time
              <input
                className={inputClass}
                value={form.time}
                onChange={(e) => update("time", e.target.value)}
              />
            </label>
          </div>

          <label className="flex flex-col gap-1 text-xs font-medium text-[var(--color-text-secondary)]">
            Venue
            <input
              className={inputClass}
              value={form.venue}
              onChange={(e) => update("venue", e.target.value)}
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-[var(--color-text-secondary)]">
            Price
            <input
              className={inputClass}
              value={form.price}
              onChange={(e) => update("price", e.target.value)}
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-[var(--color-text-secondary)]">
            Description
            <textarea
              className={`${inputClass} min-h-[96px] resize-y`}
              value={form.description}
              onChange={(e) => update("description", e.target.value)}
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-[var(--color-text-secondary)]">
            Links (comma-separated)
            <input
              className={inputClass}
              value={form.links}
              onChange={(e) => update("links", e.target.value)}
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-[var(--color-text-secondary)]">
            Categories (comma-separated slugs)
            <input
              className={inputClass}
              value={form.categories}
              onChange={(e) => update("categories", e.target.value)}
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-[var(--color-text-secondary)]">
            Regions (comma-separated slugs)
            <input
              className={inputClass}
              value={form.regions}
              onChange={(e) => update("regions", e.target.value)}
            />
          </label>

          {error && (
            <div className="rounded-lg border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40 px-3 py-2 text-xs text-red-700 dark:text-red-400">
              {error}
            </div>
          )}
        </div>

        <div className="sticky bottom-0 flex justify-end gap-2 border-t border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => void handleSave()}
            disabled={saving}
            className="rounded-lg bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] px-3 py-1.5 text-sm font-medium text-white transition-colors disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
