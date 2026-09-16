import { useEffect, useRef, useState } from "react";

import { ImageList, Text } from "@ansavva/design-system";

import type { RunAsset, RunFeedRow } from "../../types";
import { ApertureSpinner } from "../common/Aperture";
import { ActionMenu } from "../common/ActionMenu";
import { MediaThumb } from "../media/MediaThumb";
import { expectedOutputs } from "../run/aspect";
import { elapsedSince, inFlight, relativeTime, type DayGroup } from "../run/feedTime";
import { outputMenu } from "../run/OutputTile";
import { PromoteDrawer, isVideoAsset } from "../run/PromoteDrawer";
import { refOfOutput } from "../run/seed";
import { useRunActions } from "../run/useRunActions";

/**
 * The narrowest a tile may be, in px. Eleven rem — the feed's floor for a
 * still — so a picture is the same size on both layouts and switching does
 * not rescale the wall.
 */
const TILE_MIN_PX = 176;

/** What the grid draws before it has been measured, and under jsdom. */
const DEFAULT_COLUMNS = 3;

/**
 * How many tiles fit across the box.
 *
 * `ImageList.Root` takes a column COUNT, not an `auto-fill` — its native leaf
 * cannot express one, so the web leaf does not either — and the count depends
 * on how wide the feed is: two on a phone, six on a wide desk with the
 * sidebar open, seven with it folded. Measured off the wrapper with a
 * `ResizeObserver`, so folding the sidebar reflows the wall rather than
 * leaving it at the count the window implied.
 */
function useColumns(ref: React.RefObject<HTMLElement | null>): number {
  const [columns, setColumns] = useState(DEFAULT_COLUMNS);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const measure = () =>
      setColumns(Math.max(2, Math.floor(element.clientWidth / TILE_MIN_PX)));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return columns;
}

interface Props {
  groups: DayGroup[];
  now: number;
  /** Open a run — a tile's press. */
  onOpen: (row: RunFeedRow, output?: number) => void;
}

/**
 * The same runs as the feed, drawn as a wall of their outputs.
 *
 * **The unit is still the run's output, not a file.** This is the feed's rows
 * — the same pages, the same filters, the same day groups — with the plan
 * folded away: a square per output, the design system's `ImageList`, and the
 * run's word and time on a bar that shows on hover. A press opens the run in
 * the lightbox exactly as the feed's tile does, so the two layouts are one
 * screen at two zoom levels and not a second place. It is not the Files tab's
 * Media view over `runs/` — that was tried and taken out (`WEB_APP.md`):
 * a folder listing knows nothing of which run made what, and this does.
 *
 * **A clip plays on its own here.** The feed's tiles preview on hover because
 * a wall of moving pictures over a plan column is noise; this IS the wall of
 * pictures, and the ask was that it move. `MediaThumb`'s `autoplay` plays
 * only what is on screen — see the prop for the budget.
 *
 * **`ImageList.Item` is not drawn, and this is deliberate.** `Item` owns a
 * plain `<img src>`: it cannot re-sign an expired presign, lazy-load, or play
 * a clip, and `MediaThumb` is the one place this app draws media so that
 * every tile does all three. `Root` gives the grid and `ItemBar` the caption;
 * the tile between them is this file's own `<li>` with the same box `Item`
 * would have drawn — square, clipped — around the app's media element. The
 * `⋮` is a sibling of the clipped box rather than inside it, for the reason
 * `OutputTile` gives: the menu's panel is positioned, not portalled, and an
 * `overflow-hidden` around it cuts it off at the tile's edge.
 */
export function RunTiles({ groups, now, onOpen }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const columns = useColumns(box);
  const [promoting, setPromoting] = useState<{
    row: RunFeedRow;
    asset: RunAsset;
  } | null>(null);

  return (
    <div ref={box} className="flex flex-col gap-5">
      {groups.map((group) => (
        <section
          key={group.label}
          aria-label={group.label}
          className="flex flex-col gap-3"
        >
          <Text variant="caption" tone="muted">
            {group.label}
          </Text>
          <ImageList.Root columns={columns} gap="sm" data-testid="run-tiles">
            {group.rows.map((row) => (
              <RunTileSet
                key={row.id}
                row={row}
                now={now}
                onOpen={onOpen}
                onPromote={(asset) => setPromoting({ row, asset })}
              />
            ))}
          </ImageList.Root>
        </section>
      ))}

      {promoting && (
        <PromoteDrawer
          asset={promoting.asset}
          runCharacters={promoting.row.characters}
          onClose={() => setPromoting(null)}
        />
      )}
    </div>
  );
}

/**
 * One run's tiles: an output each, or the placeholders the feed row would
 * draw — shimmer while it is out, a dashed frame for a draft, a word for a
 * run that came back with nothing. Every placeholder opens the run too: a
 * draft has to be findable here, not only in the feed.
 */
function RunTileSet({
  row,
  now,
  onOpen,
  onPromote,
}: {
  row: RunFeedRow;
  now: number;
  onOpen: Props["onOpen"];
  onPromote: (asset: RunAsset) => void;
}) {
  const actions = useRunActions(row);

  if (inFlight(row.status)) {
    return (
      <>
        {Array.from({ length: expectedOutputs(row) }, (_, i) => (
          <PlaceholderTile
            key={i}
            row={row}
            testId="in-flight-tile"
            className="studio-shimmer border border-line"
            onOpen={() => onOpen(row)}
          >
            {i === 0 && (
              <>
                <ApertureSpinner
                  size="lg"
                  label={`Run ${row.status}`}
                  className="text-muted"
                />
                <Text
                  variant="caption"
                  family="mono"
                  tone="muted"
                  className="tabular-nums"
                >
                  {elapsedSince(row.submitted ?? row.created, now)}
                </Text>
              </>
            )}
          </PlaceholderTile>
        ))}
      </>
    );
  }

  if (row.outputs.length > 0) {
    return (
      <>
        {row.outputs.map((asset, index) => (
          <RunTile
            key={asset.node}
            row={row}
            asset={asset}
            index={index}
            now={now}
            onOpen={() => onOpen(row, index)}
            onPromote={() => onPromote(asset)}
            actions={actions}
          />
        ))}
      </>
    );
  }

  if (row.status === "draft") {
    return (
      <PlaceholderTile
        row={row}
        testId="draft-tile"
        className="border border-dashed border-line bg-surface-alt/40"
        onOpen={() => onOpen(row)}
      >
        <Text variant="caption" tone="muted">
          Not run yet.
        </Text>
      </PlaceholderTile>
    );
  }

  return (
    <PlaceholderTile
      row={row}
      testId="empty-tile"
      className="border border-line bg-surface-alt/40"
      onOpen={() => onOpen(row)}
    >
      <Text
        variant="caption"
        tone="muted"
        className={row.error ? "text-danger" : ""}
      >
        {row.error ? "Failed" : "Nothing came back."}
      </Text>
    </PlaceholderTile>
  );
}

/**
 * One output. The square, the opening button over it, the `⋮`, and the bar.
 */
function RunTile({
  row,
  asset,
  index,
  now,
  onOpen,
  onPromote,
  actions,
}: {
  row: RunFeedRow;
  asset: RunAsset;
  index: number;
  now: number;
  onOpen: () => void;
  onPromote: () => void;
  actions: ReturnType<typeof useRunActions>;
}) {
  const video = isVideoAsset(asset) || row.kind === "video";
  const label = `Output ${index + 1} of ${row.outputs.length}`;
  const menu = outputMenu(row, asset, index, actions, onPromote);

  return (
    <li className="group relative aspect-square">
      <div className="relative size-full overflow-hidden border border-line bg-card">
        {/* The tile is the opening button; the bar and the menu are siblings
            of it, because a button cannot contain a button. */}
        <button
          type="button"
          onClick={onOpen}
          aria-label={`Open ${label}`}
          className="block size-full"
        >
          <MediaThumb
            nodeId={asset.node}
            url={asset.url}
            name={asset.name}
            isVideo={video}
            aspect="auto"
            fit="cover"
            autoplay={video}
            className="size-full"
            drag={refOfOutput(row, asset, index)}
          />
        </button>

        {/* The run's word and when, on hover and focus — always-on scrims over
            a wall of pictures would be the plan column back in another shape.
            `pointer-events-none` so a press on the bar still opens the run. */}
        <ImageList.ItemBar
          title={row.model}
          subtitle={relativeTime(row.created, now)}
          className="pointer-events-none opacity-0 transition-opacity
                     group-hover:opacity-100 group-focus-within:opacity-100
                     motion-reduce:transition-none"
        />
      </div>

      <ActionMenu
        label={label}
        actions={menu}
        overlay
        vertical
        className="absolute right-2 top-2 opacity-0 focus-within:opacity-100
                   group-hover:opacity-100 pointer-coarse:opacity-100
                   motion-reduce:transition-none"
      />
    </li>
  );
}

/**
 * A square that stands for an output that is not here yet, or never came.
 */
function PlaceholderTile({
  row,
  testId,
  className,
  onOpen,
  children,
}: {
  row: RunFeedRow;
  testId: string;
  className: string;
  onOpen: () => void;
  children: React.ReactNode;
}) {
  return (
    <li className="aspect-square">
      <button
        type="button"
        data-testid={testId}
        onClick={onOpen}
        aria-label={`Open run ${row.status}`}
        className={`flex size-full flex-col items-center justify-center gap-2 ${className}`}
      >
        {children}
      </button>
    </li>
  );
}
