import { IconButton } from "@ansavva/design-system";

import type { RunAsset, RunFeedRow } from "../../types";
import { assetLabel } from "../../utils/format";
import {
  DownloadIcon,
  PlayIcon,
  PromoteIcon,
  RerunIcon,
  UpscaleIcon,
  UseInPromptIcon,
} from "../common/icons";
import { ratioOf } from "./aspect";
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
 * **Every control is a glyph in a corner, and the picture is the rest.** The
 * foot used to be a 2x2 grid of labelled buttons, which on a 150px tile in a
 * four-across feed covered a third of the frame — and a hover turns those
 * buttons live, so a press aimed at the picture under them ran Animate or
 * Upscale on it instead of opening it. The word was worth a scrim of its own
 * when a run had a column to itself; here it is worth less than the picture.
 * `IconButton intent="overlay"` is the package's role for a glyph over a
 * photograph, `label` is the accessible name and the tooltip both, and every
 * one of these actions is offered again, in words, in the opened run.
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
    <div className="group relative overflow-hidden border border-line bg-card">
      {/* The tile is the opening button; its frame is on the wrapper above. */}
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Open ${label}`}
        className="block w-full"
      >
        <MediaThumb
          nodeId={asset.node}
          url={asset.url}
          name={asset.name}
          isVideo={video}
          aspect={video ? "video" : "portrait"}
          ratio={ratioOf(row)}
          fit="cover"
        />
      </button>

      {/* Top corners: fetch the bytes, or hand the picture to the bar. */}
      <div className={`absolute right-2 top-2 flex gap-1 ${HIDDEN}`}>
        <IconButton
          label={`Download ${assetLabel(asset.name)}`}
          size="sm"
          intent="overlay"
          className={`bg-overlay-scrim/60 ${LIVE}`}
          onClick={() => void actions.download(asset)}
        >
          <DownloadIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
        </IconButton>
        {/* A still only — a reference is a picture, and a clip cannot be one. */}
        {!video && (
          <IconButton
            label="Use in prompt"
            size="sm"
            intent="overlay"
            className={`bg-overlay-scrim/60 ${LIVE}`}
            onClick={() => actions.useInPrompt(asset, index)}
          >
            <UseInPromptIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
          </IconButton>
        )}
      </div>

      {/* The foot: what to MAKE from this output. One row along the bottom
          edge, so what it covers is a strip rather than half the frame. */}
      <div
        className={`absolute inset-x-2 bottom-2 flex flex-wrap justify-end gap-1 ${HIDDEN}`}
      >
        <OverlayAction
          icon={<RerunIcon className={GLYPH} />}
          label="Run again with this"
          onClick={() => actions.outputAgain(asset, index)}
        />
        {!video && (
          <OverlayAction
            icon={<UpscaleIcon className={GLYPH} />}
            label="Upscale"
            onClick={() => actions.upscale(asset, index)}
          />
        )}
        {!video && (
          <OverlayAction
            icon={<PlayIcon className="size-3.5 fill-current stroke-none" />}
            label="Start frame"
            onClick={() => actions.animate(asset, index)}
          />
        )}
        {isPromotable(asset) && (
          <OverlayAction
            icon={<PromoteIcon className={GLYPH} />}
            label="Promote"
            onClick={onPromote}
          />
        )}
      </div>
    </div>
  );
}

const GLYPH = "size-3.5 fill-none stroke-current stroke-[1.5]";

/**
 * A group of controls that is not there yet.
 *
 * **`pointer-events-none` is the half that was missing.** `opacity-0` hides a
 * control and leaves it clickable, so the two overlays above — four buttons
 * across the foot of every still, two in the corner — were catching presses
 * aimed at the picture under them. Pressing a run's output ran Animate or
 * Upscale on it instead of opening it, which on a touch screen (where a hover
 * state may never arrive at all) is every press the tile gets.
 *
 * The group never takes a press back, at any width: it is a strip across the
 * whole picture, and letting hover make IT live would put an invisible sheet
 * over the frame between the glyphs. `LIVE` is what wakes the buttons.
 */
const HIDDEN =
  "pointer-events-none opacity-0 transition-opacity group-hover:opacity-100 " +
  "group-focus-within:opacity-100 motion-reduce:transition-none";

/** The other half, on each control: alive exactly when the group is visible. */
const LIVE =
  "pointer-events-none group-hover:pointer-events-auto group-focus-within:pointer-events-auto";

/**
 * One glyph over media: the same treatment as the two in the top corner, so
 * the tile carries one kind of control rather than two.
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
    <IconButton
      label={label}
      size="sm"
      intent="overlay"
      className={`bg-overlay-scrim/60 ${LIVE}`}
      onClick={onClick}
    >
      {icon}
    </IconButton>
  );
}
