import { useId, type ReactElement } from "react";

import {
  Badge,
  Button,
  Chip,
  IconButton,
  Select,
  Text,
  Toggle,
  ToggleGroup,
} from "@ansavva/design-system";

import type { AttachRole, Attachment } from "../../context/CreateBarContext";
import type { ModelEntry, RunKind, SnapshotProp } from "../../types";
import {
  FrameEndIcon,
  LockIcon,
  PencilIcon,
  PersonIcon,
  PlayIcon,
  TrashIcon,
} from "../common/icons";
import { ROLES_BY_KIND, ROLE_WORDS, fieldFor } from "./roles";

const ROLE_ICONS: Record<
  AttachRole,
  (props: { className?: string }) => ReactElement
> = {
  reference: PersonIcon,
  input: PencilIcon,
  start: PlayIcon,
  end: FrameEndIcon,
};

const ICON = "size-4 fill-none stroke-current stroke-[1.5]";

/**
 * The strip under the bar: what each attached image is FOR.
 *
 * **Mode-specific, and read off the model.** Image mode offers Reference and
 * Edit; video mode offers Animate (the start frame), End frame and Reference,
 * then the clip's duration inline. A role the selected model has no input for
 * is not drawn — `fieldFor` answers from the registry entry's `images`, so a
 * still model never shows a start frame and a model with no reference list
 * never shows Reference.
 *
 * **Highlighting a role is what opens the drawer.** The drawer supplies images
 * for whichever role is highlighted, so the cell is the control: press its
 * name or its empty slot and the drawer below fills that role. A second press
 * on the highlighted one closes it.
 *
 * Nothing here is a `<button>` wrapping a `<button>`: each cell is a group,
 * the name is a `Chip`, the empty slot is a `Button`, and the thumbs carry
 * their own × as a sibling of the picture.
 */
export function CreateModeStrip({
  kind,
  entry,
  attachments,
  role,
  onRole,
  onDetach,
  onClear,
  keep,
  onKeep,
  params,
  onParams,
}: {
  kind: RunKind;
  entry: ModelEntry;
  attachments: readonly Attachment[];
  /** The highlighted role, or none. */
  role: AttachRole | null;
  onRole: (role: AttachRole | null) => void;
  /** Take one attachment off, by its index in `attachments`. */
  onDetach: (index: number) => void;
  onClear: () => void;
  keep: boolean;
  onKeep: (keep: boolean) => void;
  params: Record<string, unknown>;
  onParams: (next: Record<string, unknown>) => void;
}) {
  const roles = ROLES_BY_KIND[kind].filter(
    (each) => fieldFor(each, entry) !== null,
  );
  const duration = kind === "video" ? durationOf(entry) : null;

  return (
    // No overflow rule here: the Duration listbox drops below the row, and a
    // scroll container would scroll the whole strip up to reach it instead.
    <div
      className="flex flex-wrap items-stretch border-b border-line md:flex-nowrap"
      data-mode-strip=""
    >
      {roles.map((each) => {
        const words = ROLE_WORDS[each];
        const Icon = ROLE_ICONS[each];
        const held = attachments
          .map((attachment, index) => ({ attachment, index }))
          .filter(({ attachment }) => attachment.role === each);
        const on = role === each;
        const toggle = () => onRole(on ? null : each);
        return (
          <div
            key={each}
            role="group"
            aria-label={words.label}
            data-role-cell={each}
            className={`flex min-w-0 flex-1 items-center gap-3 border-r border-line px-3 py-2 ${
              on ? "bg-surface-alt" : ""
            }`}
          >
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <Chip
                pressed={on}
                size="sm"
                className="w-fit gap-1.5 rounded-none border-0 px-0"
                onClick={toggle}
              >
                <Icon className={ICON} />
                {words.label}
              </Chip>
              <Text variant="caption" tone="muted" className="hidden md:block">
                {words.hint}
              </Text>
            </div>
            <div className="flex shrink-0 gap-1">
              {held.map(({ attachment, index }) => (
                <AttachmentThumb
                  key={`${attachment.ref.node}-${index}`}
                  attachment={attachment}
                  onDetach={() => onDetach(index)}
                />
              ))}
              {/* One slot for a role that holds one image and already does is
                  filled; a list role always has room for one more. */}
              {(held.length === 0 || each === "reference") && (
                <Button
                  intent="secondary"
                  size="sm"
                  wrap
                  className="size-16 rounded-none border-dashed p-1 text-[11px] leading-tight"
                  aria-pressed={on}
                  onClick={toggle}
                >
                  Select image below
                </Button>
              )}
            </div>
          </div>
        );
      })}

      {duration && (
        <DurationCell
          prop={duration}
          value={params.duration}
          onChange={(next) => onParams({ ...params, duration: next })}
        />
      )}

      <div className="flex shrink-0 flex-col justify-center gap-1 px-2">
        <IconButton
          size="sm"
          pressed={keep}
          label={
            keep
              ? "Keep these images for the next send (on)"
              : "Keep these images for the next send"
          }
          className="rounded-none"
          onClick={() => onKeep(!keep)}
        >
          <LockIcon />
        </IconButton>
        <IconButton
          size="sm"
          label="Clear images"
          className="rounded-none"
          disabled={attachments.length === 0}
          onClick={onClear}
        >
          <TrashIcon />
        </IconButton>
      </div>
    </div>
  );
}

/**
 * One attached image: the picture, its role, and the way off.
 *
 * The × is a sibling of the picture rather than a child of a button around
 * it, for the reason every tile in this app is built that way — a control
 * inside a control is invalid HTML the browser resolves by dropping one.
 */
export function AttachmentThumb({
  attachment,
  onDetach,
}: {
  attachment: Attachment;
  onDetach: () => void;
}) {
  const { ref, role } = attachment;
  return (
    <div
      className="relative size-16 shrink-0 border border-line bg-bg"
      title={ref.name}
    >
      <img src={ref.url} alt="" className="size-full object-cover" />
      <Badge
        size="sm"
        intent="neutral"
        className="absolute left-0 top-0 rounded-none"
      >
        {ROLE_WORDS[role].label}
      </Badge>
      <IconButton
        intent="overlay"
        size="sm"
        label={`Remove ${ref.name}`}
        className="absolute bottom-0 right-0 size-6 rounded-none"
        onClick={onDetach}
      >
        <TrashIcon className="size-3.5" />
      </IconButton>
    </div>
  );
}

/**
 * The clip's length, inline — the one parameter worth a place on the strip.
 *
 * Read off the registry snapshot rather than the live schema: the strip is
 * drawn on every keystroke and the schema is a provider round trip. An enum
 * is a row of toggles (`4s 6s 8s`); a range is a select over the whole
 * integers in it, floored at one second because a provider that advertises
 * `-1` means "auto" and this control has no word for that.
 */
function DurationCell({
  prop,
  value,
  onChange,
}: {
  prop: SnapshotProp;
  value: unknown;
  onChange: (next: number) => void;
}) {
  const label = useId();
  const current =
    typeof value === "number"
      ? value
      : typeof prop.default === "number"
        ? prop.default
        : null;
  const choices = durationChoices(prop);

  return (
    <div className="flex shrink-0 items-center gap-3 border-r border-line px-3 py-2">
      <Text id={label} as="span" className="text-sm font-medium text-ink">
        Duration
      </Text>
      {choices.length > 0 && choices.length <= 6 ? (
        <ToggleGroup.Root
          aria-labelledby={label}
          value={current === null ? [] : [String(current)]}
          onValueChange={(next: string[]) => {
            const chosen = next[0];
            if (chosen !== undefined) onChange(Number(chosen));
          }}
          size="sm"
        >
          {choices.map((each) => (
            <Toggle key={each} value={String(each)} className="rounded-none">
              {each}s
            </Toggle>
          ))}
        </ToggleGroup.Root>
      ) : (
        <div className="w-24">
          <Select
            aria-labelledby={label}
            options={choices.map((each) => ({
              value: String(each),
              label: `${each}s`,
            }))}
            value={current === null ? null : String(current)}
            onValueChange={(next: string) => onChange(Number(next))}
          />
        </div>
      )}
    </div>
  );
}

function durationOf(entry: ModelEntry): SnapshotProp | null {
  const prop = entry.snapshot?.duration;
  return prop && typeof prop === "object" ? (prop as SnapshotProp) : null;
}

/** The seconds a duration prop allows, as whole numbers. */
export function durationChoices(prop: SnapshotProp): number[] {
  if (Array.isArray(prop.enum)) {
    return prop.enum.filter((each): each is number => typeof each === "number");
  }
  const low = Math.max(
    1,
    typeof prop.minimum === "number" ? Math.ceil(prop.minimum) : 1,
  );
  const high =
    typeof prop.maximum === "number" ? Math.floor(prop.maximum) : low + 9;
  const out: number[] = [];
  for (let each = low; each <= high && out.length < 60; each += 1)
    out.push(each);
  return out;
}
