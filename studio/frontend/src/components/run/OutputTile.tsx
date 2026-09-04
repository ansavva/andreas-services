import { IconButton, buttonClass } from "@ansavva/design-system";

import type { RunAsset, RunFeedRow } from "../../types";
import {
  DownloadIcon,
  PlayIcon,
  PromoteIcon,
  RerunIcon,
  UpscaleIcon,
  UseInPromptIcon,
} from "../common/icons";
import { MediaThumb } from "../media/MediaThumb";
import { isPromotable, isVideoAsset } from "./PromoteDrawer";
import type { useRunActions } from "./useRunActions";

/**
 * One output in the feed: the picture, and on hover what can be done with it.
 *
 * **The tile is a button and every control on it is a sibling.** A button
 * cannot contain a button — the rule `MediaTile` and `EntityCard` already
 * live by — so the overlays are positioned over the opening button rather
 * than inside it, and the frame sits on the wrapper. They appear on hover and
 * on focus-within, so a keyboard reaches them the way a pointer does.
 *
 * **No trash on a tile.** The mockup draws one; nothing in the API deletes a
 * single output — `DELETE /api/runs/<id>` takes the run and its folder, and a
 * node delete would leave the run's record pointing at bytes that are gone.
 * Trash is on the run, in its action row.
 *
 * The icon-only controls are `IconButton intent="overlay"` — the package's
 * roles for a glyph over a photograph. The labelled row at the foot lays its
 * own scrim down first, which is what makes a WORD legible over arbitrary
 * pixels; the package leaves that to the caller on purpose.
 */
export function OutputTile({
  row,
  asset,
  index,
  onOpen,
  onPromote,
  actions,
}: {
  row: RunFeedRow;
  asset: RunAsset;
  /** 0-based position in `row.outputs`. */
  index: number;
  onOpen: () => void;
  onPromote: () => void;
  actions: ReturnType<typeof useRunActions>;
}) {
  const video = isVideoAsset(asset) || row.kind === "video";
  const label = `Output ${index + 1} of ${row.outputs.length}`;

  return (
    <div className="group relative overflow-hidden rounded-none border border-line bg-card">
      {/* eslint-disable-next-line studio/no-hand-rolled-button -- the tile is
          the opening button; its frame is on the wrapper above. */}
      <button type="button" onClick={onOpen} aria-label={`Open ${label}`} className="block w-full">
        <MediaThumb
          nodeId={asset.node}
          url={asset.url}
          name={asset.name}
          isVideo={video}
          aspect={video ? "video" : "portrait"}
          fit="cover"
        />
      </button>

      {video && (
        // Says "this plays" without being a control — the tile is the press.
        <span
          aria-hidden="true"
          className="pointer-events-none absolute left-1/2 top-1/2 flex size-11 -translate-x-1/2 -translate-y-1/2
                     items-center justify-center border border-overlay-muted bg-overlay-scrim/55 text-overlay-ink"
        >
          <PlayIcon className="size-5 fill-current stroke-none" />
        </span>
      )}

      {/* Top corners: fetch the bytes, or hand the picture to the bar. */}
      <div
        className="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-focus-within:opacity-100
                   group-hover:opacity-100 motion-reduce:transition-none"
      >
        <IconButton
          label={`Download ${asset.name}`}
          size="sm"
          intent="overlay"
          className="rounded-none bg-overlay-scrim/60"
          onClick={() => void actions.download(asset)}
        >
          <DownloadIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
        </IconButton>
        <IconButton
          label="Use in prompt"
          size="sm"
          intent="overlay"
          className="rounded-none bg-overlay-scrim/60"
          onClick={() => actions.useInPrompt(asset, index)}
        >
          <UseInPromptIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
        </IconButton>
      </div>

      {/* The foot: what to MAKE from this output. */}
      <div
        className="absolute inset-x-2 bottom-2 grid grid-cols-2 gap-1.5 opacity-0 transition-opacity
                   group-focus-within:opacity-100 group-hover:opacity-100 motion-reduce:transition-none"
      >
        <OverlayAction icon={<RerunIcon className={GLYPH} />} label="Again" onClick={() => actions.outputAgain(asset, index)} />
        {!video && (
          <OverlayAction icon={<UpscaleIcon className={GLYPH} />} label="Upscale" onClick={() => actions.upscale(asset, index)} />
        )}
        {!video && (
          <OverlayAction icon={<PlayIcon className="size-3.5 fill-current stroke-none" />} label="Animate" onClick={() => actions.animate(asset, index)} />
        )}
        {isPromotable(asset) && (
          <OverlayAction icon={<PromoteIcon className={GLYPH} />} label="Promote" onClick={onPromote} />
        )}
      </div>
    </div>
  );
}

const GLYPH = "size-3.5 fill-none stroke-current stroke-[1.5]";

/**
 * A labelled control over media: the scrim is laid down here, under the
 * package's secondary fill, so the word reads over any frame.
 */
function OverlayAction({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={buttonClass({
        intent: "secondary",
        size: "sm",
        className: "rounded-none border border-overlay-muted bg-overlay-scrim/65 text-overlay-ink hover:bg-overlay-hover",
      })}
    >
      {icon}
      {label}
    </button>
  );
}
