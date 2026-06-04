import { useLayoutEffect, useRef } from "react";
import { Chip } from "@/components/ui";
import { RichText } from "@/components/RichText";
import { LocationPicker } from "@/components/edit/LocationPicker";
import { LabelEditor } from "@/components/edit/LabelEditor";
import { formatDateTimeLine } from "@/utils/formatters";
import type {
  EventDraft,
  Label,
  Location,
  PublicEvent,
  PublicLocation,
  PublicSubEvent,
  SubEventDraft,
} from "@/types";

export function locationLine(location: PublicLocation | null): string | null {
  if (!location) return null;
  return location.address ? `${location.name}, ${location.address}` : location.name;
}

/**
 * Editing context threaded through the detail view. When present, fields render
 * as inputs styled identically to their published form, so an admin sees the
 * live preview take shape as they type.
 */
export interface EventEditContext {
  draft: EventDraft;
  onChange: (patch: Partial<EventDraft>) => void;
  onSubChange: (subId: string, patch: Partial<SubEventDraft>) => void;
  locations: Location[];
  labels: Label[];
  onCreateLocation: (name: string) => Promise<Location>;
  onCreateLabel: (name: string) => Promise<Label>;
}

// Textarea that grows to fit its content so an inline-edited title/description
// keeps the exact line wrapping and vertical rhythm of the rendered text.
function AutoTextarea({
  value,
  onChange,
  className,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  className: string;
  placeholder?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  return (
    <textarea
      ref={ref}
      rows={1}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className={className}
    />
  );
}

// Inline date + optional time range inputs, sharing the serif styling of the
// row they sit in. Used for both the event header and each occurrence.
function DateTimeFields({
  startDate,
  startTime,
  endTime,
  onChange,
}: {
  startDate: string;
  startTime: string | null;
  endTime: string | null;
  onChange: (patch: { start_date?: string; start_time?: string | null; end_time?: string | null }) => void;
}) {
  const field =
    "border-b border-dashed border-[var(--color-border)] bg-transparent outline-none focus:border-[var(--color-text-primary)]";
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <input
        type="date"
        value={startDate}
        onChange={(e) => onChange({ start_date: e.target.value })}
        className={field}
      />
      <input
        type="time"
        value={startTime ?? ""}
        onChange={(e) => onChange({ start_time: e.target.value || null })}
        className={field}
      />
      <span aria-hidden>–</span>
      <input
        type="time"
        value={endTime ?? ""}
        onChange={(e) => onChange({ end_time: e.target.value || null })}
        className={field}
      />
    </span>
  );
}

function SubEventRow({
  sub,
  edit,
  draft,
}: {
  sub: PublicSubEvent;
  edit?: EventEditContext;
  draft?: SubEventDraft;
}) {
  if (edit && draft) {
    return (
      <li className="border-b border-[var(--color-border)] py-5">
        <div className="font-serif text-lg leading-tight text-[var(--color-text-primary)]">
          <DateTimeFields
            startDate={draft.start_date}
            startTime={draft.start_time}
            endTime={draft.end_time}
            onChange={(patch) => edit.onSubChange(draft.subevent_id, patch)}
          />
        </div>
        <div className="mt-2">
          <LocationPicker
            value={draft.location_id_override}
            locations={edit.locations}
            onChange={(id) => edit.onSubChange(draft.subevent_id, { location_id_override: id })}
            onCreate={edit.onCreateLocation}
            placeholder="Override location (inherits event)"
          />
        </div>
        <div className="mt-3">
          <LabelEditor
            selectedIds={draft.event_label_ids}
            labels={edit.labels}
            onChange={(ids) =>
              edit.onSubChange(draft.subevent_id, {
                event_label_ids: ids,
                event_labels_overridden: true,
              })
            }
            onCreate={edit.onCreateLabel}
          />
          <p className="mt-1 text-[10px] text-[var(--color-text-muted)]">
            Editing labels overrides the event&apos;s labels for this date.
          </p>
        </div>
      </li>
    );
  }

  const when = formatDateTimeLine(sub.start_date, sub.start_time, sub.end_time);
  return (
    <li className="border-b border-[var(--color-border)] py-5">
      <div
        className={
          when
            ? "font-serif text-lg leading-tight text-[var(--color-text-primary)]"
            : "font-serif text-lg italic leading-tight text-[var(--color-text-muted)]"
        }
      >
        {when || "Date to be announced"}
      </div>
      {locationLine(sub.location) && (
        <div className="eyebrow mt-2 text-[var(--color-text-secondary)]">
          {locationLine(sub.location)}
        </div>
      )}
      {sub.event_labels.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {sub.event_labels.map((l) => (
            <Chip key={l.id} label={l.name} />
          ))}
        </div>
      )}
    </li>
  );
}

/**
 * Presentational render of a single event in the public detail layout. Shared
 * by the public detail page and the admin inline preview so what an admin sees
 * matches the published page exactly. Passing `edit` turns the same layout into
 * an in-place editor — fields become inputs styled like their published form.
 */
export function EventDetailView({
  event,
  edit,
}: {
  event: PublicEvent;
  edit?: EventEditContext;
}) {
  const labels = [...event.event_labels, ...event.location_labels];
  const image = event.images.find((i) => i.url)?.url ?? null;
  const place = locationLine(event.location);
  const when = formatDateTimeLine(event.start_date, event.start_time, event.end_time);
  // The date/location band carries top+bottom rules; only draw it when there's
  // something to sit between them, so a date-less, location-less event doesn't
  // render as an empty boxed strip.
  const metaBand =
    "eyebrow mt-6 flex flex-wrap items-center gap-x-3 gap-y-2 border-y border-[var(--color-rule)] py-4 text-[var(--color-text-secondary)]";

  return (
    <article>
      {edit ? (
        <div className="eyebrow text-[var(--color-text-muted)]">
          <LabelEditor
            selectedIds={edit.draft.event_label_ids}
            labels={edit.labels}
            onChange={(ids) => edit.onChange({ event_label_ids: ids })}
            onCreate={edit.onCreateLabel}
          />
        </div>
      ) : (
        labels.length > 0 && (
          <p className="eyebrow text-[var(--color-text-muted)]">
            {labels.map((l) => l.name).join(" · ")}
          </p>
        )
      )}

      {edit ? (
        <AutoTextarea
          value={edit.draft.title}
          onChange={(v) => edit.onChange({ title: v })}
          placeholder="Event title"
          className="mt-4 w-full resize-none overflow-hidden bg-transparent font-serif text-hero font-light leading-[1.02] text-[var(--color-text-primary)] outline-none"
        />
      ) : (
        <h1 className="mt-4 font-serif text-hero font-light text-[var(--color-text-primary)]">
          {event.title}
        </h1>
      )}

      {edit ? (
        <div className={metaBand}>
          <DateTimeFields
            startDate={edit.draft.start_date}
            startTime={edit.draft.start_time}
            endTime={edit.draft.end_time}
            onChange={(patch) => edit.onChange(patch)}
          />
          <span aria-hidden>—</span>
          <LocationPicker
            value={edit.draft.location_id}
            locations={edit.locations}
            onChange={(id) => edit.onChange({ location_id: id })}
            onCreate={edit.onCreateLocation}
          />
        </div>
      ) : when || place ? (
        <div className={metaBand}>
          {when && <span>{when}</span>}
          {when && place && <span aria-hidden>—</span>}
          {place && <span>{place}</span>}
        </div>
      ) : null}

      {image && (
        <img
          src={image}
          alt={event.title}
          className="mt-8 aspect-[16/9] w-full object-cover grayscale"
        />
      )}

      {edit ? (
        <AutoTextarea
          value={edit.draft.description}
          onChange={(v) => edit.onChange({ description: v })}
          placeholder="Description"
          className="mt-8 block w-full max-w-prose resize-none overflow-hidden whitespace-pre-line bg-transparent text-base leading-relaxed text-[var(--color-text-secondary)] outline-none sm:text-lg"
        />
      ) : (
        event.description && (
          <RichText
            text={event.description}
            className="mt-8 max-w-prose whitespace-pre-line text-base leading-relaxed text-[var(--color-text-secondary)] sm:text-lg"
          />
        )
      )}

      {event.sub_events.length > 0 ? (
        <section className="mt-12">
          <h2 className="eyebrow text-[var(--color-text-muted)]">Dates</h2>
          <ul className="mt-4 border-t border-[var(--color-rule)]">
            {event.sub_events.map((s) => (
              <SubEventRow
                key={s.subevent_id}
                sub={s}
                edit={edit}
                draft={edit?.draft.sub_events.find((d) => d.subevent_id === s.subevent_id)}
              />
            ))}
          </ul>
        </section>
      ) : event.no_upcoming_dates ? (
        <p className="mt-12 text-sm text-[var(--color-text-muted)]">No upcoming dates.</p>
      ) : null}
    </article>
  );
}
