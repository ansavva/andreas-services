import { useState, type ReactNode } from "react";

import { IconButton, Text } from "@ansavva/design-system";

import { assetLabel, formatBytes } from "../../utils/format";
import { EmptyState } from "../common/EmptyState";
import { SwapIcon } from "../common/icons";
import type { AttachRef } from "../../context/CreateBarContext";
import { MediaPlayer, type MediaPlayerControls } from "./MediaPlayer";
import { FIT, type ZoomState } from "./useZoom";

/** What a pane needs to draw a picture — the four fields every asset carries. */
export interface ComparePicture {
  node: string;
  url?: string | null;
  name?: string;
  size?: number;
  /** What a drag of this pane carries — `MediaPlayer`'s `drag`. An object by default. */
  drag?: AttachRef;
}

interface Props {
  /** The pinned picture — the one on the stage when Compare was pressed. */
  a: ComparePicture;
  /** The one beside it; `null` until something is picked. */
  b: ComparePicture | null;
  /** A and B change places. */
  onSwap: () => void;
  /** Pane A's controls — the zoom keys' way in. See `MediaPlayer`. */
  onControlsChange?: (controls: MediaPlayerControls | null) => void;
}

/**
 * Two stills side by side, zooming together.
 *
 * **One zoom for both panes, and that is what makes it a comparison.** Each
 * player would otherwise hold its own — a wheel over the left one leaves the
 * right at the fit, and the two pictures are then at different sizes and
 * different places, which is two pictures rather than one comparison. The
 * state is held here and handed to both as a controlled value; a gesture on
 * either arrives at `setZoom` and both redraw at the same scale about the
 * same point. Two outputs of one run share a size, so the same offset lands
 * on the same detail in each.
 *
 * **B is whatever the caller thought likeliest, or empty — and an empty pane
 * says so.** The rule both viewers follow is that Compare pins the picture on
 * the stage, and the next tile pressed goes beside it. The opened run starts
 * B on its other output, because two outputs of one send is the comparison
 * a person opens Compare for; the open file starts it empty, because a
 * neighbour in a folder is no likelier than any other.
 *
 * The keys reach the shared zoom through pane A's controls — `+`, `-` and
 * `0` from `useKeyboardNav` land on one player and both move, because the
 * state they change is this component's.
 *
 * Side by side from `md`; stacked below it, where two panes across a phone
 * would each be narrower than a thumbnail.
 */
export function CompareStage({ a, b, onSwap, onControlsChange }: Props) {
  const [zoom, setZoom] = useState<ZoomState>(FIT);

  return (
    <div
      data-testid="compare-stage"
      className="grid h-full w-full min-h-0 grid-rows-2 gap-2 md:grid-cols-2 md:grid-rows-1"
    >
      <Pane
        label="A"
        picture={a}
        zoom={zoom}
        onZoomChange={setZoom}
        onControlsChange={onControlsChange}
      />
      <Pane
        label="B"
        picture={b}
        zoom={zoom}
        onZoomChange={setZoom}
        action={
          b && (
            <IconButton label="Swap sides" size="sm" onClick={onSwap}>
              <SwapIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
            </IconButton>
          )
        }
      />
    </div>
  );
}

function Pane({
  label,
  picture,
  zoom,
  onZoomChange,
  onControlsChange,
  action,
}: {
  label: "A" | "B";
  picture: ComparePicture | null;
  zoom: ZoomState;
  onZoomChange: (next: ZoomState) => void;
  onControlsChange?: (controls: MediaPlayerControls | null) => void;
  action?: ReactNode;
}) {
  return (
    <figure
      className="flex min-h-0 min-w-0 flex-col items-center gap-1"
      aria-label={`Compare ${label}`}
    >
      {picture ? (
        <div className="min-h-0 w-full flex-1">
          <MediaPlayer
            key={picture.node}
            nodeId={picture.node}
            url={picture.url}
            name={picture.name}
            aspect="auto"
            fit="contain"
            zoomable
            zoom={zoom}
            onZoomChange={onZoomChange}
            onControlsChange={onControlsChange}
            drag={picture.drag ?? true}
            className="h-full w-full border border-line"
            actions={
              <Text
                variant="caption"
                family="mono"
                className="bg-overlay-scrim/60 px-1.5 py-0.5 text-overlay-ink"
              >
                {label}
              </Text>
            }
          />
        </div>
      ) : (
        <div className="flex min-h-0 w-full flex-1 items-center justify-center border border-dashed border-line">
          <EmptyState title="Press a picture to put it here." />
        </div>
      )}
      {/* The caption row carries the swap as well — beside the picture's
          name rather than over the picture, where the player's own chrome
          already sits. */}
      <figcaption className="flex h-8 items-center gap-2">
        <Text variant="caption" family="mono" tone="muted" className="tabular-nums">
          {picture
            ? `${assetLabel(picture.name)}${picture.size ? ` · ${formatBytes(picture.size)}` : ""}`
            : " "}
        </Text>
        {action}
      </figcaption>
    </figure>
  );
}
