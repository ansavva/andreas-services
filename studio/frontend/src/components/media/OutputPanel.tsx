import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { Text } from "@ansavva/design-system";

import { MediaPlayer } from "./MediaPlayer";
import { MediaThumb } from "./MediaThumb";
import type { RunAsset } from "../../types";
import { formatBytes } from "../../utils/format";

/**
 * A run's output: watchable here, and openable properly.
 *
 * **Two complaints, one component.** A video output was a poster in a tile — to
 * see it move you left the page for the object screen, which is the exact trip
 * the inline player exists to end. And the tile was a `<button>`, so a
 * command-click did nothing: the browser has no new-tab gesture for a button,
 * so the app was discarding the one affordance every person already has for
 * "not here, over there".
 *
 * The media plays in place, and the caption under it is a real `<a href>` —
 * command, control, shift and middle click go to the browser, a plain click to
 * the router. The same bargain `PageBar`'s crumbs make.
 *
 * **The link cannot wrap the player.** The player is full of buttons, and an
 * anchor containing a button is neither one thing nor the other to a keyboard
 * or a screen reader. So the caption carries the link and says where it goes.
 *
 * `fit="contain"` without exception: an output is the thing being judged, and
 * `cover` crops to fill the box — which on anything but a square clip quietly
 * cut the edges off the shot.
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

  /** Every gesture that means "somewhere else" belongs to the browser. */
  const open = (event: React.MouseEvent) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
      return;
    event.preventDefault();
    navigate(to);
  };

  return (
    <div className="flex min-w-0 flex-col gap-1 border border-line bg-card p-1">
      {isVideo ? (
        <MediaPlayer
          nodeId={asset.node}
          url={asset.url}
          name={asset.name}
          isVideo
          aspect={sole ? "auto" : "square"}
          fit="contain"
        />
      ) : (
        <a
          href={to}
          onClick={open}
          className="block focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <MediaThumb
            nodeId={asset.node}
            url={asset.url}
            name={asset.name}
            aspect={sole ? "auto" : "square"}
            fit="contain"
            className="w-full rounded-none"
          />
        </a>
      )}

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
          <Text variant="caption" tone="muted" className="truncate font-mono">
            {asset.name}
          </Text>
          {badge}
        </span>
        {asset.size !== undefined && (
          <Text
            variant="caption"
            tone="muted"
            className="font-mono tabular-nums"
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
