import { useCallback, useState } from "react";
import { Link } from "react-router-dom";

import { Button, Text } from "@ansavva/design-system";

import { getFavorites } from "../../apis/studio";
import { useCreateBar } from "../../context/CreateBarContext";
import { FAVORITES_GRID_KEY, useFavorites } from "../../hooks/useFavorites";
import { useResource } from "../../hooks/useResource";
import type { FavoriteEntry } from "../../types";
import { downloadNode } from "../../utils/download";
import { MEDIA_GRID } from "../../utils/grid";
import { FAVORITES_PATH, objectPath } from "../../utils/location";
import { EmptyState } from "../common/EmptyState";
import { LoadError } from "../common/LoadError";
import { SectionLoading } from "../common/SectionLoading";
import { linkButtonClass } from "../common/linkButtonClass";
import { DownloadIcon, HeartFilledIcon, UseInPromptIcon } from "../common/icons";
import type { MenuAction } from "../common/ActionMenu";
import { MediaTile } from "../browse/MediaTile";

/**
 * How many tiles home shows before it stops and points at the whole screen.
 *
 * Two rows on the widest grid (`MEDIA_GRID` is eight across at `lg`). Home is
 * an index of three things and the favorites are the first of them; a hundred
 * tiles here would make the other two unreachable without scrolling, which is
 * exactly the complaint that retired the Recent grid.
 */
const HOME_TILES = 16;

/** What "Show more" adds on the favorites screen itself. */
const PAGE = 60;

/** Every tile-menu line's glyph, at the size a line of text carries. */
const MENU_GLYPH = "size-4 shrink-0 fill-none stroke-current stroke-[1.5]";

/**
 * The favorites grid, at two sizes.
 *
 * `preview` is home's first two rows with a link to the rest; `full` is the
 * `/favorites` screen, which pages. One component, because they are the same
 * grid and the difference is a number — the mistake `EntitySections` was
 * written to avoid, where home and an index page grew two subtly different
 * copies of one list.
 *
 * ## Why this pages by growing the request rather than by appending a cursor
 *
 * Every other paged surface in this app accumulates: `useMedia` holds an array
 * and appends the next page onto it. That is right for a recursive walk of the
 * library, where re-reading page one means re-walking a branch.
 *
 * Favorites are not that. The whole list is one query on one partition, the
 * hydration is `ceil(n / 100)` batched reads, and the only per-page cost is
 * presigning — so asking for a bigger page is nearly the same request. What
 * that buys is that a heart pressed anywhere in the app invalidates ONE cache
 * entry and this grid is simply correct again, with no accumulated array to
 * splice an id out of and no cursor to re-derive. An accumulating version of
 * this screen has a bug in it the moment somebody unfavorites the third tile.
 */
export function FavoritesSection({
  variant = "full",
}: {
  variant?: "preview" | "full";
}) {
  const [limit, setLimit] = useState(variant === "preview" ? HOME_TILES : PAGE);

  const { data, loading, error, reload } = useResource(
    [...FAVORITES_GRID_KEY, limit],
    useCallback(() => getFavorites(undefined, limit), [limit]),
  );

  const items: FavoriteEntry[] = data?.entries ?? [];
  const total = data?.total ?? 0;

  const bar = useCreateBar();
  const favorites = useFavorites();

  const tileActions = useCallback(
    (file: FavoriteEntry): MenuAction[] => [
      ...(file.kind === "image"
        ? [
            {
              key: "reference",
              label: "Use as reference",
              icon: <UseInPromptIcon className={MENU_GLYPH} />,
              onSelect: () =>
                bar.attach(
                  { node: file.id, url: file.url, name: file.name, kind: "object" },
                  "reference",
                ),
            },
          ]
        : []),
      {
        key: "favorite",
        label: "Remove from favorites",
        icon: <HeartFilledIcon className="size-4 fill-current stroke-none" />,
        onSelect: () => favorites.setFavorite(file.id, false),
      },
      {
        key: "download",
        label: "Download",
        icon: <DownloadIcon className={MENU_GLYPH} />,
        onSelect: () => void downloadNode(file.id),
      },
    ],
    [bar, favorites],
  );

  return (
    <section className="flex flex-col gap-3" aria-label="Favorites">
      {variant === "preview" && (
        <div className="flex items-baseline justify-between gap-3 border-b border-line pb-2">
          <Text variant="title">
            Favorites{" "}
            <span className="font-mono text-sm text-muted tabular-nums">({total})</span>
          </Text>
          {/* Only once there is more than home is showing. A "See all" beside a
              complete list is a link to the page you are already reading. */}
          {total > items.length && (
            <Link to={FAVORITES_PATH} className={linkButtonClass()}>
              See all
            </Link>
          )}
        </div>
      )}

      {loading && <SectionLoading label="Loading favorites" />}
      {error && (
        <LoadError what="favorites" message={error} onRetry={reload} />
      )}

      {!loading && !error && items.length === 0 && (
        <EmptyState
          title="Nothing favorited yet."
          // The instruction is the whole empty state. A favorites screen with
          // no favorites is the one screen where a person cannot work out what
          // to do from what is in front of them — the control that fills it is
          // on a different page.
          // The gesture moved: the heart over a tile became a line in the
          // tile's own `⋮`, so the sentence that names it has to move with it
          // or it sends people looking for a control that is not there.
          hint="Open any image or video's ⋯ menu and add it to favorites."
        />
      )}

      {items.length > 0 && (
        <div className={MEDIA_GRID}>
          {items.map((file) => (
            <MediaTile
              key={file.id}
              file={file}
              // No checkbox: there is no move, copy or delete toolbar behind
              // this grid, so a selection here would collect an answer nothing
              // asks for. `MediaTile` draws one only when given somewhere to
              // send it.
              onOpen={() => undefined}
              // What this screen can do to a picture, which is less than the
              // browser can: there is no folder here to move it within and no
              // rename field to open. Taking it off the screen is the one this
              // grid owes — it is where the heart used to be.
              actions={tileActions(file)}
              draggableRef={file.kind === "image"}
              // The viewer steps through the favorites, not through the folder
              // each one happens to live in — `?in=fav`. Opening a picture from
              // here and finding yourself in somebody's `reference` folder is
              // the exact teleport `ViewerSource` exists to stop.
              to={objectPath(file.id, { in: "fav", id: null })}
            />
          ))}
        </div>
      )}

      {variant === "full" && total > items.length && (
        <div className="flex justify-center">
          <Button size="sm" intent="secondary" onClick={() => setLimit(limit + PAGE)}>
            Show more ({total - items.length} left)
          </Button>
        </div>
      )}

      {data?.truncated && (
        <Text variant="caption" tone="muted">
          More favorites exist than this can show at once.
        </Text>
      )}
    </section>
  );
}
