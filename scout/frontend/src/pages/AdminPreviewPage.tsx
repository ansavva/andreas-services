import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "@/api";
import { Header } from "@/components/Header";
import { EventDetailView, type EventEditContext } from "@/components/EventDetailView";
import { Button, ErrorBanner, Spinner } from "@/components/ui";
import type {
  AdminEvent,
  EventDraft,
  Label,
  Location,
  PublicEvent,
  SubEvent,
} from "@/types";

function buildDraft(ev: AdminEvent, subs: SubEvent[]): EventDraft {
  return {
    title: ev.title ?? "",
    description: ev.description_md ?? "",
    start_date: ev.start_date ?? "",
    start_time: ev.start_time ?? null,
    end_time: ev.end_time ?? null,
    location_id: ev.location_id ?? null,
    event_label_ids: ev.event_label_ids ?? [],
    sub_events: subs.map((s) => ({
      subevent_id: s.subevent_id,
      start_date: s.start_date ?? "",
      start_time: s.start_time ?? null,
      end_time: s.end_time ?? null,
      location_id_override: s.location_id_override ?? null,
      event_labels_overridden: !!s.event_labels_overridden,
      event_label_ids: s.event_label_ids ?? [],
    })),
  };
}

const sameIds = (a: string[], b: string[]) =>
  a.length === b.length && a.every((x, i) => x === b[i]);

/**
 * Admin preview of an event rendered as a full page — what the public detail
 * page will look like once published. An Edit toggle turns the same layout into
 * an in-place editor (fields keep their published styling while typing); Save
 * persists changes to the event and its occurrences, Cancel discards the draft.
 */
export function AdminPreviewPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const api = useApi();
  const [event, setEvent] = useState<PublicEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit state: the live draft, the snapshot to diff/restore against, and the
  // reference lists the location/label pickers need.
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<EventDraft | null>(null);
  const [original, setOriginal] = useState<EventDraft | null>(null);
  const [locations, setLocations] = useState<Location[]>([]);
  const [labels, setLabels] = useState<Label[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!eventId) return;
    setLoading(true);
    setError(null);
    try {
      const [preview, detail] = await Promise.all([
        api.previewEvent(eventId),
        api.getEvent(eventId),
      ]);
      setEvent(preview);
      const d = buildDraft(detail.event, detail.subevents);
      setDraft(d);
      setOriginal(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Not found");
    } finally {
      setLoading(false);
    }
  }, [api, eventId]);

  useEffect(() => {
    load();
  }, [load]);

  async function enterEdit() {
    setSaveError(null);
    try {
      const [locs, lbls] = await Promise.all([
        api.listLocations(),
        api.listLabels("event"),
      ]);
      setLocations(locs.locations);
      setLabels(lbls.labels);
      setOriginal(draft);
      setEditing(true);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not load editor data");
    }
  }

  function cancelEdit() {
    setDraft(original);
    setEditing(false);
    setSaveError(null);
  }

  async function save() {
    if (!eventId || !draft || !original) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api.updateEvent(eventId, {
        title: draft.title,
        description: draft.description,
        start_date: draft.start_date,
        start_time: draft.start_time,
        end_time: draft.end_time,
        location_id: draft.location_id,
        event_label_ids: draft.event_label_ids,
      });

      const origSubs = new Map(original.sub_events.map((s) => [s.subevent_id, s]));
      for (const sub of draft.sub_events) {
        const o = origSubs.get(sub.subevent_id);
        const labelsChanged =
          !o ||
          !sameIds(sub.event_label_ids, o.event_label_ids) ||
          sub.event_labels_overridden !== o.event_labels_overridden;
        const changed =
          !o ||
          sub.start_date !== o.start_date ||
          sub.start_time !== o.start_time ||
          sub.end_time !== o.end_time ||
          sub.location_id_override !== o.location_id_override ||
          labelsChanged;
        if (!changed) continue;
        const body: Record<string, unknown> = {
          start_date: sub.start_date,
          start_time: sub.start_time,
          end_time: sub.end_time,
          location_id_override: sub.location_id_override,
        };
        // Only send labels when the admin actually touched them, so an
        // inheriting occurrence isn't silently frozen into an override.
        if (labelsChanged) body.event_label_ids = sub.event_label_ids;
        await api.updateSubevent(eventId, sub.subevent_id, body);
      }

      await load();
      setEditing(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not save changes");
    } finally {
      setSaving(false);
    }
  }

  const onCreateLocation = useCallback(
    async (name: string) => {
      const loc = (await api.createLocation({ name, timezone: "UTC" })) as Location;
      setLocations((prev) => [...prev, loc]);
      return loc;
    },
    [api]
  );

  const onCreateLabel = useCallback(
    async (name: string) => {
      const lbl = (await api.createLabel("event", name)) as Label;
      setLabels((prev) => [...prev, lbl]);
      return lbl;
    },
    [api]
  );

  const editCtx: EventEditContext | undefined = useMemo(() => {
    if (!editing || !draft) return undefined;
    return {
      draft,
      onChange: (patch) => setDraft((d) => (d ? { ...d, ...patch } : d)),
      onSubChange: (subId, patch) =>
        setDraft((d) =>
          d
            ? {
                ...d,
                sub_events: d.sub_events.map((s) =>
                  s.subevent_id === subId ? { ...s, ...patch } : s
                ),
              }
            : d
        ),
      locations,
      labels,
      onCreateLocation,
      onCreateLabel,
    };
  }, [editing, draft, locations, labels, onCreateLocation, onCreateLabel]);

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <Header />
      <main className="mx-auto max-w-3xl px-5 py-10 sm:px-6 sm:py-14">
        <div className="flex items-center justify-between gap-4">
          <Link
            to="/admin?tab=review"
            className="eyebrow inline-flex items-center gap-2 text-[var(--color-text-muted)] no-underline hover:text-[var(--color-text-primary)]"
          >
            ← Back to review
          </Link>
          {!loading && !error && event && (
            <div className="flex items-center gap-2">
              {editing ? (
                <>
                  <Button variant="ghost" onClick={cancelEdit} disabled={saving}>
                    Cancel
                  </Button>
                  <Button variant="primary" onClick={save} disabled={saving}>
                    {saving ? "Saving…" : "Save"}
                  </Button>
                </>
              ) : (
                <Button onClick={enterEdit}>Edit</Button>
              )}
            </div>
          )}
        </div>

        {loading && (
          <div className="flex justify-center py-24">
            <Spinner />
          </div>
        )}
        {error && (
          <div className="mt-10">
            <ErrorBanner message={error} />
          </div>
        )}
        {saveError && (
          <div className="mt-6">
            <ErrorBanner message={saveError} />
          </div>
        )}

        {!loading && !error && event && (
          <div className="mt-10">
            <EventDetailView event={event} edit={editCtx} />
          </div>
        )}
      </main>
    </div>
  );
}
