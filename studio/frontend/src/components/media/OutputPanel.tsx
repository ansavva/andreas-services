import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { Text } from "@ansavva/design-system";

import { MediaThumb } from "./MediaThumb";
import type { RunAsset } from "../../types";
import { useFavorites } from "../../hooks/useFavorites";
import { ActionMenu, type MenuAction } from "../common/ActionMenu";
import { FavoriteMark, favoriteAction } from "../common/Favorite";
import { DownloadIcon } from "../common/icons";
import { downloadNode } from "../../utils/download";
import { assetLabel, formatBytes } from "../../utils/format";
import { kindOfFile } from "../../utils/media";

/** Every menu line's glyph, at the size a line of text carries. */
const GLYPH = "size-4 shrink-0 fill-none stroke-current stroke-[1.5]";

/**
 * A scene's take: the picture, openable like any other.
 *
 * **A clip here is a tile, not a player.** It was a `MediaPlayer` — watchable
 * in place, with the caption under it the only link out — and that made a
 * scene's take the one video in the app a press did not open: a feed tile
 * opens its run, a folder tile opens the viewer, and a take played where it
 * stood, under a page that kept scrolling, with the viewer a small caption
 * away. So it draws as every other output does — poster, duration, a hover
 * preview — and the press opens the viewer with `?in=scene`, which puts every
 * other take one arrow key away.
 *
 * **Both the tile and the caption are real `<a href>`s.** Command, control,
 * shift and middle click go to the browser — "not here, over there" is the
 * one affordance every person already has, and a `<button>` would discard it
 * — and a plain click to the router. The same bargain `PageBar`'s crumbs make.
 *
 * `fit="contain"` without exception: an output is the thing being judged, and
 * `cover` crops to fill the box — which on anything but a square clip quietly
 * cut the edges off the shot. A clip takes a 16:9 box because an unloaded
 * `<video>` is 0px tall and a take has no plan to read a shape off; a still
 * is drawn at its own.
 *
 * **It carries the `⋮` and the heart every other media tile carries.** A
 * scene's assembled take is a video like any other, and this was the one
 * tile in the app with no menu on it at all: the cut it is made of offered
 * `Add to favorites` on every clip's `⋮`, and the finished scene — the thing
 * a person actually keeps — offered nothing, so the only way to favorite one
 * was to open it and find the line in the viewer's `⋯`. Same placement as
 * `OutputTile`: the mark top left, the trigger top right, drawn on hover and
 * always where there is no pointer to hover with.
 */
export function OutputPanel({
  asset,
  sole,
  to,
  badge,
  action,
}: {
  asset: RunAsset;
  /** The only output — then it is the subject of the page, not a tile in a grid. */
  sole: boolean;
  to: string;
  /** A scene shows "earlier" on every cut but the current one. */
  badge?: ReactNode;
  /**
   * A control acting on this output, on the caption row.
   *
   * A **sibling** of the caption link rather than a child: the caption is an
   * `<a>`, and a button inside an anchor is neither one thing nor the other to
   * a keyboard. Outside the card it read as debris between the output and
   * whatever came next, which is what this slot exists to stop.
   */
  action?: ReactNode;
}) {
  const navigate = useNavigate();
  const isVideo = (asset.content_type ?? "").startsWith("video/");
  const favorites = useFavorites();

  // The API refuses a favorite on anything that is not an image or a video,
  // so the line is offered only where it would be honoured — and the kind is
  // read the way the API reads it, `kindOfFile`, extension first. A take is
  // always a clip; the check is here because this panel takes whatever asset
  // it is handed. See `services/favorites.py`.
  const kind = kindOfFile(asset.name ?? "", asset.content_type);
  const menu: MenuAction[] = [
    ...(kind === "image" || kind === "video"
      ? [favoriteAction(asset.node, favorites.isFavorite(asset.node), favorites.toggle)]
      : []),
    {
      key: "download",
      label: "Download",
      icon: <DownloadIcon className={GLYPH} />,
      onSelect: () => void downloadNode(asset.node),
    },
  ];

  /** Every gesture that means "somewhere else" belongs to the browser. */
  const open = (event: React.MouseEvent) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
      return;
    event.preventDefault();
    navigate(to);
  };

  return (
    // `group relative` for the two things drawn over the picture, and no
    // `overflow-hidden` on it: the menu's panel is absolutely positioned
    // rather than portalled (`ItemActions` says why), and a clip at the top of
    // a page is exactly where one opens downward out of its own box.
    <div className="group relative flex min-w-0 flex-col gap-1 rounded-md border border-line bg-card p-1">
      <a
        href={to}
        onClick={open}
        aria-label={`Open ${assetLabel(asset.name)}`}
        className="block focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        <MediaThumb
          nodeId={asset.node}
          url={asset.url}
          poster={asset.poster}
          duration={asset.duration}
          name={asset.name}
          isVideo={isVideo}
          aspect={isVideo ? "video" : sole ? "auto" : "square"}
          fit="contain"
          className="w-full"
        />
      </a>

      {/* Top left, clear of the menu — the corner a run's output keeps it in.
          The card's own `p-1` is the extra 4px in both offsets. */}
      <FavoriteMark id={asset.node} className="left-3 top-3" />

      {/* A sibling of the link, never a child: a button inside an anchor is
          neither one thing nor the other to a keyboard — the bargain the
          caption row's `action` slot already makes. */}
      <ActionMenu
        label={assetLabel(asset.name)}
        actions={menu}
        overlay
        vertical
        className="absolute right-3 top-3 opacity-0 focus-within:opacity-100
                   group-hover:opacity-100 pointer-coarse:opacity-100
                   motion-reduce:transition-none"
      />

      {/* The caption and anything acting on this output share one row, so the
          control sits against the name it belongs to rather than under the
          card. */}
      <div className="flex min-w-0 items-end justify-between gap-2 px-1 pb-1">
      {/* `flex-col`, because two `Text` captions are inline spans: without it
          the name and the size ran together as "flex-draft.mp42.7 MB". */}
      <a
        href={to}
        onClick={open}
        className="flex min-w-0 flex-col hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        <span className="flex min-w-0 items-center gap-2">
          <Text variant="caption" family="mono" tone="muted" className="truncate">
            {assetLabel(asset.name)}
          </Text>
          {badge}
        </span>
        {asset.size !== undefined && (
          <Text
            variant="caption" family="mono"
            tone="muted"
            className="tabular-nums"
          >
            {formatBytes(asset.size)}
          </Text>
        )}
      </a>
        {action}
      </div>
    </div>
  );
}
