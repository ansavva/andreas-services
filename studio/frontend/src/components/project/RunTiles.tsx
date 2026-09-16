import { memo, useCallback, useEffect, useRef, useState, type ReactElement } from "react";

import { ImageList, Masonry, Text } from "@ansavva/design-system";

import type { RunAsset, RunFeedRow } from "../../types";
import { ApertureSpinner } from "../common/Aperture";
import { ActionMenu } from "../common/ActionMenu";
import { MediaThumb } from "../media/MediaThumb";
import { expectedOutputs, ratioOf } from "../run/aspect";
import { elapsedSince, inFlight, relativeTime, type DayGroup } from "../run/feedTime";
import { outputMenu } from "../run/OutputTile";
import { PromoteDrawer, isVideoAsset } from "../run/PromoteDrawer";
import { refOfOutput } from "../run/seed";
import { useRunActions } from "../run/useRunActions";

/**
 * The narrowest a column may be, in px. Eleven rem — the feed's floor for a
 * still — so a picture is the same size on both layouts and switching does
 * not rescale the wall.
 */
const TILE_MIN_PX = 176;

/** What the wall draws before it has been measured, and under jsdom. */
const DEFAULT_COLUMNS = 3;

/**
 * How many columns fit across the box.
 *
 * `Masonry` takes a column COUNT, not an `auto-fill` — its native leaf
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
 * folded away: a tile per output, the run's word and time on a bar that
 * shows on hover. A press opens the run in the lightbox exactly as the feed's
 * tile does, so the two layouts are one screen at two zoom levels and not a
 * second place. It is not the Files tab's Media view over `runs/` — that was
 * tried and taken out (`WEB_APP.md`): a folder listing knows nothing of which
 * run made what, and this does.
 *
 * **`Masonry`, not `ImageList`, and every tile at its own shape.** The first
 * cut was `ImageList`, whose tiles are squares — and a 16:9 clip in a square
 * is a third of itself, a 9:16 still a torso with no head. The feed already
 * knows each run's shape (`ratioOf`, off the plan), so the wall gives every
 * tile that ratio and packs the columns: `Masonry` deals tiles round-robin
 * into N columns, height-blind, which is what a wall of mixed shapes wants.
 * `ImageList.ItemBar` stays for the caption; it is an overlay and reads no
 * grid. The tiles are handed to `Masonry` FLAT, one element each, because it
 * counts children and a fragment of three is one child to it — so a run's
 * tiles are built in a loop here rather than by a component per run, and
 * `useRunActions` is called by the tile.
 *
 * **A clip plays on its own here.** The feed's tiles preview on hover because
 * a wall of moving pictures over a plan column is noise; this IS the wall of
 * pictures, and the ask was that it move. `MediaThumb`'s `autoplay` plays
 * only what is on screen — see the prop for the budget.
 *
 * The `⋮` is a sibling of the clipped box rather than inside it, for the
 * reason `OutputTile` gives: the menu's panel is positioned, not portalled,
 * and an `overflow-hidden` around it cuts it off at the tile's edge.
 */
export function RunTiles({ groups, now, onOpen }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const columns = useColumns(box);
  const [promoting, setPromoting] = useState<{
    row: RunFeedRow;
    asset: RunAsset;
  } | null>(null);
  // Stable, so a memoised tile is not re-rendered for a new closure.
  const promote = useCallback(
    (row: RunFeedRow, asset: RunAsset) => setPromoting({ row, asset }),
    [],
  );

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
          <Masonry columns={columns} gap="sm" data-testid="run-tiles">
            {group.rows.flatMap((row) => tilesOf(row, now, onOpen, promote))}
          </Masonry>
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
 * One run's tiles, flat: an output each, or the placeholders the feed row
 * would draw — shimmer while it is out, a dashed frame for a draft, a word
 * for a run that came back with nothing. Every placeholder opens the run
 * too: a draft has to be findable here, not only in the feed.
 */
function tilesOf(
  row: RunFeedRow,
  now: number,
  onOpen: Props["onOpen"],
  onPromote: (row: RunFeedRow, asset: RunAsset) => void,
): ReactElement[] {
  if (inFlight(row.status)) {
    return Array.from({ length: expectedOutputs(row) }, (_, i) => (
      <PlaceholderTile
        key={`${row.id}:${i}`}
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
    ));
  }

  if (row.outputs.length > 0) {
    // `when` is a string, so the tick that moves `now` only reaches a tile
    // whose wording actually changed — see `RunTile`'s memo.
    const when = relativeTime(row.created, now);
    return row.outputs.map((asset, index) => (
      <RunTile
        key={asset.node}
        row={row}
        asset={asset}
        index={index}
        when={when}
        onOpen={onOpen}
        onPromote={onPromote}
      />
    ));
  }

  if (row.status === "draft") {
    return [
      <PlaceholderTile
        key={row.id}
        row={row}
        testId="draft-tile"
        className="border border-dashed border-line bg-surface-alt/40"
        onOpen={() => onOpen(row)}
      >
        <Text variant="caption" tone="muted">
          Not run yet.
        </Text>
      </PlaceholderTile>,
    ];
  }

  return [
    <PlaceholderTile
      key={row.id}
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
    </PlaceholderTile>,
  ];
}

/**
 * One output: the picture at the plan's shape, the opening button over it,
 * the `⋮`, and the bar.
 *
 * **Memoised, and its props are chosen so the memo holds.** While a run is
 * out, `useNow` ticks the feed once a second and every tile used to rebuild
 * — its menu, its closures, its `MediaThumb` — for a timestamp that changes
 * once a minute. With twenty clips decoding on the same thread, that tick
 * was the difference between a wall that keeps up and one that drags. So:
 * the time comes in as a string, and the two callbacks take the row and the
 * asset as arguments rather than closing over them, so both are stable.
 */
const RunTile = memo(function RunTile({
  row,
  asset,
  index,
  when,
  onOpen,
  onPromote,
}: {
  row: RunFeedRow;
  asset: RunAsset;
  index: number;
  /** `relativeTime` of the run's creation, already worded. */
  when: string;
  onOpen: Props["onOpen"];
  onPromote: (row: RunFeedRow, asset: RunAsset) => void;
}) {
  const actions = useRunActions(row);
  const video = isVideoAsset(asset) || row.kind === "video";
  const label = `Output ${index + 1} of ${row.outputs.length}`;
  const menu = outputMenu(row, asset, index, actions, () => onPromote(row, asset));
  const ratio = ratioOf(row);

  return (
    <div className="group relative" style={{ aspectRatio: ratio }}>
      <div className="relative size-full overflow-hidden rounded-md border border-line bg-card">
        {/* The tile is the opening button; the bar and the menu are siblings
            of it, because a button cannot contain a button. */}
        <button
          type="button"
          onClick={() => onOpen(row, index)}
          aria-label={`Open ${label}`}
          className="block size-full"
        >
          <MediaThumb
            nodeId={asset.node}
            url={asset.url}
            name={asset.name}
            isVideo={video}
            ratio={ratio}
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
          subtitle={when}
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
    </div>
  );
});

/**
 * A frame at the run's shape that stands for an output that is not here
 * yet, or never came.
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
    <button
      type="button"
      data-testid={testId}
      onClick={onOpen}
      aria-label={`Open run ${row.status}`}
      style={{ aspectRatio: ratioOf(row) }}
      className={`flex w-full flex-col items-center justify-center gap-2 rounded-md ${className}`}
    >
      {children}
    </button>
  );
}
