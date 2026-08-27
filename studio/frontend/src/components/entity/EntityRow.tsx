import { Badge, Text } from "@ansavva/design-system";

import { MediaThumb } from "../media/MediaThumb";

interface Props {
  title: string;
  subtitle: string;
  status: string;
  /**
   * The pointer, not a bare URL.
   *
   * A presigned URL expires, and re-signing addresses a **node** — so a row
   * handed only a `url` can never repair itself. This used to be
   * `thumbUrl: string | null` for exactly that reason: nothing on the row knew
   * which node the picture was.
   */
  thumb: { node: string; url: string } | null;
  /** A position in the cut. Movies number their scenes; a project's listings do not. */
  index?: number;
  onOpen: () => void;
}

/**
 * One scene, movie or other entity in a list: a thumbnail, two lines, a status.
 *
 * **Written twice before this.** A project's Scenes and Movies tabs shared a
 * `ListRow`, and a movie's own page open-coded the same row again with a number
 * in front of it — same markup, same sizes, one of them with a thumbnail that
 * could not re-sign. The number is the only thing that ever differed, so it is a
 * prop.
 */
export function EntityRow({ title, subtitle, status, thumb, index, onOpen }: Props) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-md border border-line bg-card p-2 text-left
                 transition-colors hover:bg-surface-alt
                 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      {index !== undefined && (
        <Text variant="body" className="w-8 shrink-0 text-right tabular-nums">
          {index}
        </Text>
      )}

      {thumb ? (
        <MediaThumb
          nodeId={thumb.node}
          url={thumb.url}
          name=""
          aspect="auto"
          className="size-14 shrink-0 rounded-md border border-line"
        />
      ) : (
        <span className="size-14 shrink-0 rounded-md border border-line bg-surface-alt" />
      )}

      <span className="min-w-0 flex-1">
        {/* `block` on the caption: `Text variant="caption"` is an inline span,
            so a subtitle under a title runs onto the same line without it —
            the bug `EntityCard` carried in production. */}
        <Text variant="body" className="truncate">
          {title}
        </Text>
        <Text variant="caption" tone="muted" className="block truncate">
          {subtitle}
        </Text>
      </span>

      <Badge intent="neutral">{status}</Badge>
    </button>
  );
}
