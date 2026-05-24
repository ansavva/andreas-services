import { useMemo, useState } from "react";
import { Calendar, CheckCircle2, Edit3, MapPin, XCircle } from "lucide-react";
import type { Category, Event } from "@/types";
import { useAdminApi, useAdminEvents, type EventEditFields } from "@/hooks/useAdminApi";
import { useCategories } from "@/hooks/useCategories";
import { CategoryChips } from "@/components/CategoryChips";
import { SkeletonCard } from "@/components/SkeletonCard";
import { EventEditModal } from "@/components/admin/EventEditModal";
import { formatDate } from "@/utils/formatters";

type StatusFilter = "pending" | "published" | "all";

const STATUS_TABS: { key: StatusFilter; label: string }[] = [
  { key: "pending", label: "Pending" },
  { key: "published", label: "Published" },
  { key: "all", label: "All" },
];

interface RegionTagsProps {
  regions: string[];
}

function RegionTags({ regions }: RegionTagsProps) {
  if (!regions || regions.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {regions.map((r) => (
        <span
          key={r}
          className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)]"
        >
          <MapPin size={11} />
          {r}
        </span>
      ))}
    </div>
  );
}

interface AdminEventCardProps {
  event: Event;
  categories: Category[];
  status: StatusFilter;
  selected: boolean;
  onToggleSelect: (id: string) => void;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onUnpublish: (id: string) => void;
  onEdit: (event: Event) => void;
  busy: boolean;
}

function AdminEventCard({
  event,
  categories,
  status,
  selected,
  onToggleSelect,
  onApprove,
  onReject,
  onUnpublish,
  onEdit,
  busy,
}: AdminEventCardProps) {
  const isPending = event.status === "pending";
  const isPublished = event.status === "published";

  return (
    <article className="theme-transition flex flex-col gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-card">
      <div className="flex items-start gap-3">
        {status === "pending" && isPending && (
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect(event.event_id)}
            className="mt-1 h-4 w-4 accent-[var(--color-primary)]"
            aria-label="Select event"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)] leading-snug">
              {event.event_name || "Untitled Event"}
            </h3>
            <span className="shrink-0 text-xs font-medium px-2 py-0.5 rounded-full bg-[var(--color-badge)] text-[var(--color-badge-text)]">
              {event.status}
            </span>
          </div>

          <dl className="mt-2 flex flex-col gap-1 text-xs text-[var(--color-text-secondary)]">
            {event.date && (
              <div className="flex items-center gap-1.5">
                <Calendar size={12} className="text-[var(--color-text-muted)]" />
                <dd>
                  {formatDate(event.date)}
                  {event.time ? ` · ${event.time}` : ""}
                </dd>
              </div>
            )}
            {event.venue && (
              <div className="flex items-center gap-1.5">
                <MapPin size={12} className="text-[var(--color-text-muted)]" />
                <dd>{event.venue}</dd>
              </div>
            )}
          </dl>

          <div className="mt-2 flex flex-col gap-1.5">
            <RegionTags regions={event.regions ?? []} />
            <CategoryChips slugs={event.categories ?? []} categories={categories} />
          </div>

          {(event.email_subject || event.email_sender) && (
            <p className="mt-2 text-xs text-[var(--color-text-muted)] truncate">
              <span className="font-medium">Source:</span> {event.email_subject || "(no subject)"}
              {event.email_sender ? ` — ${event.email_sender}` : ""}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-[var(--color-border)] pt-3">
        {isPending && (
          <button
            onClick={() => onApprove(event.event_id)}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-green-600 hover:bg-green-700 px-3 py-1.5 text-xs font-medium text-white transition-colors disabled:opacity-50"
          >
            <CheckCircle2 size={14} />
            Approve
          </button>
        )}
        {isPending && (
          <button
            onClick={() => onReject(event.event_id)}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg border border-red-300 dark:border-red-900 px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors disabled:opacity-50"
          >
            <XCircle size={14} />
            Reject
          </button>
        )}
        {isPublished && (
          <button
            onClick={() => onUnpublish(event.event_id)}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] transition-colors disabled:opacity-50"
          >
            <XCircle size={14} />
            Unpublish
          </button>
        )}
        <button
          onClick={() => onEdit(event)}
          disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] transition-colors disabled:opacity-50"
        >
          <Edit3 size={14} />
          Edit
        </button>
      </div>
    </article>
  );
}

export function AdminEventsSection() {
  const [status, setStatus] = useState<StatusFilter>("pending");
  const { events, loading, error, refetch } = useAdminEvents(status);
  const { categories } = useCategories();
  const api = useAdminApi();

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Event | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const pendingIds = useMemo(
    () => events.filter((e) => e.status === "pending").map((e) => e.event_id),
    [events]
  );

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const runAction = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
      setSelected(new Set());
      refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const handleSave = async (fields: EventEditFields) => {
    if (!editing) return;
    await api.updateEvent(editing.event_id, fields);
    refetch();
  };

  const allSelected = pendingIds.length > 0 && pendingIds.every((id) => selected.has(id));

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => {
              setStatus(tab.key);
              setSelected(new Set());
            }}
            className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
              status === tab.key
                ? "bg-[var(--color-primary)] text-white border-[var(--color-primary)]"
                : "border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {status === "pending" && pendingIds.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2">
          <label className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={() =>
                setSelected(allSelected ? new Set() : new Set(pendingIds))
              }
              className="h-4 w-4 accent-[var(--color-primary)]"
            />
            Select all ({pendingIds.length})
          </label>
          <button
            onClick={() => void runAction(() => api.bulkApprove([...selected]))}
            disabled={busy || selected.size === 0}
            className="inline-flex items-center gap-1.5 rounded-lg bg-green-600 hover:bg-green-700 px-3 py-1.5 text-xs font-medium text-white transition-colors disabled:opacity-50"
          >
            <CheckCircle2 size={14} />
            Approve selected ({selected.size})
          </button>
        </div>
      )}

      {actionError && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-400">
          {actionError}
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-400">
          <strong>Could not load events:</strong> {error}
        </div>
      )}

      {loading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {!loading && !error && events.length === 0 && (
        <p className="py-12 text-center text-sm text-[var(--color-text-muted)]">
          No {status === "all" ? "" : status} events.
        </p>
      )}

      {!loading && !error && events.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {events.map((ev) => (
            <AdminEventCard
              key={ev.event_id}
              event={ev}
              categories={categories}
              status={status}
              selected={selected.has(ev.event_id)}
              onToggleSelect={toggleSelect}
              onApprove={(id) => void runAction(() => api.approveEvent(id))}
              onReject={(id) => void runAction(() => api.rejectEvent(id))}
              onUnpublish={(id) => void runAction(() => api.unpublishEvent(id))}
              onEdit={setEditing}
              busy={busy}
            />
          ))}
        </div>
      )}

      {editing && (
        <EventEditModal
          event={editing}
          onClose={() => setEditing(null)}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
