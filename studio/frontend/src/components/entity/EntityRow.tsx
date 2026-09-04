import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { Badge, Text, type BadgeIntent } from "@ansavva/design-system";

import { MediaThumb } from "../media/MediaThumb";

/** A status word, with the colour it carries when the caller knows one. */
export type RowBadge = string | { label: string; intent?: BadgeIntent };

/**
 * What sits at the start of a row.
 *
 * A picture is the pointer, not a bare URL: a presigned URL expires and
 * re-signing addresses a **node**, so a row handed only a `url` could never
 * repair itself. A row with nothing to show draws the one placeholder the app
 * has — a blank square carrying the kind in mono, or nothing at all. Files and
 * folders have no picture and are not missing one, so they bring an icon.
 */
type RowThumb =
  | { node: string; url: string; isVideo?: boolean }
  | { placeholder: string }
  | { icon: ReactNode };

interface Props {
  title: string;
  /** Mono, under the title — a date, a model id, a byte count. */
  subtitle?: string;
  /** A date standing in for a name is a value, so it may be set in mono too. */
  mono?: boolean;
  status?: RowBadge | RowBadge[];
  thumb?: RowThumb | null;
  /** A position in a cut. Movies number their scenes; a project's listings do not. */
  index?: number;
  /**
   * Where opening the row goes.
   *
   * **The row is an `<a>`, which is the whole point.** Every list in this app
   * used to be a column of `<button>`s, and a button has no new-tab gesture —
   * command-click, middle-click and "copy link" all did nothing on a run, a
   * scene or a folder. A plain click is still the router's; anything modified
   * goes to the browser, the bargain `MediaTile` already makes.
   *
   * Absent for a row that opens nowhere — a file the viewer cannot draw.
   */
  to?: string;
  /**
   * What a plain click does instead of following `to`.
   *
   * An override, not the usual path: a folder inside a Files tab moves with
   * `replace` rather than a push, and a row in selection mode toggles rather
   * than opens. Without `to`, this is what makes the row pressable at all.
   */
  onOpen?: (event: React.MouseEvent) => void;
  /**
   * The list is in selection mode, so shift belongs to it.
   *
   * Shift-click is claimed twice — the browser opens a new window with it, a
   * list extends a selection with it — and only inside selection mode is the
   * list's meaning the one a person means.
   */
  selecting?: boolean;
  selected?: boolean;
  /** Before the link — a checkbox. A sibling, because a button cannot sit inside an anchor. */
  leading?: ReactNode;
  /** After the link — a per-row menu, or a metric. */
  trailing?: ReactNode;
  /** A full-width line under the row: the rename form. */
  children?: ReactNode;
}

/** Whether the browser should have this click rather than the router. */
export function isModifiedPress(event: React.MouseEvent): boolean {
  return event.metaKey || event.ctrlKey || event.altKey;
}

/**
 * One item in a list — the one row, wherever a list appears.
 *
 * **Seven components drew a row and no two agreed.** Runs were filled cards
 * with a gap between them, scenes were flush rules, files were bordered boxes
 * with a checkbox, folders were grid cards, a run's bindings were tiles with a
 * caption. Hover fills, focus rings and selected marks all differed, so the
 * same gesture read differently on every screen. This is what every one of
 * them draws now; what differs between a run and a file is data, and arrives
 * as props.
 *
 * A ruled row, not a card: the rule is on the row itself, so a list is
 * `flex flex-col` with no gap and the hairlines land flush.
 */
export function EntityRow({
  title,
  subtitle,
  mono = false,
  status,
  thumb,
  index,
  to,
  onOpen,
  selecting = false,
  selected = false,
  leading,
  trailing,
  children,
}: Props) {
  const navigate = useNavigate();
  const openable = Boolean(to || onOpen);

  const press = (event: React.MouseEvent) => {
    if (isModifiedPress(event)) return;
    if (event.shiftKey && !selecting) return;
    event.preventDefault();
    if (onOpen) onOpen(event);
    else if (to) navigate(to);
  };

  const badges = status === undefined ? [] : Array.isArray(status) ? status : [status];

  const body = (
    <>
      {index !== undefined && (
        <Text variant="body" family="mono" className="w-8 shrink-0 text-right tabular-nums">
          {index}
        </Text>
      )}

      {thumb && "icon" in thumb && thumb.icon}
      {thumb && "node" in thumb && (
        <MediaThumb
          nodeId={thumb.node}
          url={thumb.url}
          name=""
          isVideo={thumb.isVideo}
          aspect="auto"
          className="size-14 shrink-0 rounded-none border border-line"
        />
      )}
      {thumb && "placeholder" in thumb && (
        <span
          className="flex size-14 shrink-0 items-center justify-center rounded-none border border-line
                     bg-surface-alt font-mono text-xs text-muted"
        >
          {thumb.placeholder}
        </span>
      )}

      <span className="min-w-0 flex-1">
        <Text variant="body" family={mono ? "mono" : "body"} className="truncate">
          {title}
        </Text>
        {/* `block`: a caption is an inline span, and without it a subtitle
            runs onto the title's line. */}
        {subtitle && (
          <Text variant="caption" tone="muted" className="block truncate font-mono tabular-nums">
            {subtitle}
          </Text>
        )}
      </span>

      {badges.map((badge) => {
        const { label, intent } =
          typeof badge === "string" ? { label: badge, intent: undefined } : badge;
        return (
          <Badge key={label} intent={intent ?? "neutral"} className="font-mono">
            {label}
          </Badge>
        );
      })}
    </>
  );

  const main =
    "flex min-w-0 flex-1 items-center gap-3 rounded-none px-2 py-2 text-left " +
    "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary";

  return (
    // The frame is on the wrapper so a checkbox or a menu can sit *beside* the
    // link rather than inside it. `group` is for the checkbox, which hides
    // until the row is hovered.
    <div
      className={`group flex w-full flex-wrap items-center gap-2 rounded-none border-b transition-colors
                  ${openable ? "hover:bg-surface-alt" : ""}
                  ${selected ? "border-primary ring-1 ring-primary" : "border-line"}`}
    >
      {leading}

      {to ? (
        <a
          href={to}
          onClick={press}
          title={title}
          aria-current={selected ? "true" : undefined}
          className={main}
        >
          {body}
        </a>
      ) : (
        <button
          type="button"
          onClick={press}
          disabled={!onOpen}
          title={title}
          className={`${main} disabled:cursor-default disabled:opacity-60`}
        >
          {body}
        </button>
      )}

      {trailing && <span className="flex shrink-0 items-center gap-2 pe-1">{trailing}</span>}

      {children}
    </div>
  );
}
