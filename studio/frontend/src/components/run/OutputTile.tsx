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
import { ActionMenu, type MenuAction } from "../common/ActionMenu";
import { ratioOf } from "./aspect";
import { MediaThumb } from "../media/MediaThumb";
import { isPromotable, isVideoAsset } from "./PromoteDrawer";
import type { useRunActions } from "./useRunActions";

/** Every menu line's glyph, at the size a line of text carries. */
const GLYPH = "size-4 shrink-0 fill-none stroke-current stroke-[1.5]";

/**
 * One output in the feed: the picture, and a `⋮` holding what can be done
 * with it.
 *
 * **The tile is a button and the menu is a sibling.** A button cannot contain
 * a button — the rule `MediaTile` and `EntityCard` already live by — so the
 * trigger is positioned over the opening button rather than inside it, and the
 * frame sits on the wrapper.
 *
 * **Six glyphs over the picture became one menu with words in it.** Download,
 * Use in prompt, Run again, Upscale, Start frame and Promote were `opacity-0`
 * overlays in two rows, revealed on hover — and `opacity-0` hides a control
 * without disarming it, so a press aimed at the picture ran Animate or Upscale,
 * and one in the corner started a download, which navigates the window and
 * brings the app back cold. `e2e/runs.spec.ts` carries that case. On a touch
 * screen, where the hover may never arrive, it was every press the tile got:
 * the fix at the time was `pointer-events-none` on the group and a `LIVE` class
 * waking each control on hover — two classes to keep in step, on every tile,
 * to make invisible buttons safe. One trigger needs neither.
 *
 * **No trash here.** Nothing in the API deletes a single output —
 * `DELETE /api/runs/<id>` takes the run and its folder, and a node delete would
 * leave the run's record pointing at bytes that are gone. Trash is on the run,
 * in its action row.
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

  /**
   * What this output offers, in the order a person reaches for it: make
   * something from it, then take it away with you.
   *
   * **A still only, for four of them.** Every role a picture can fill is a
   * picture — a clip attached as a reference or a start frame is sent to a
   * field that refuses it — and the upscaler takes an image. Download is the
   * one that means the same thing for both.
   */
  const menu: MenuAction[] = [
    {
      key: "again",
      label: "Run again with this",
      icon: <RerunIcon className={GLYPH} />,
      onSelect: () => actions.outputAgain(asset, index),
    },
    ...(video
      ? []
      : [
          {
            key: "reference",
            label: "Use as reference",
            icon: <UseInPromptIcon className={GLYPH} />,
            onSelect: () => actions.useInPrompt(asset, index),
          },
          {
            key: "start",
            label: "Start frame",
            icon: <PlayIcon className="size-4 shrink-0 fill-current stroke-none" />,
            onSelect: () => actions.animate(asset, index),
          },
          {
            key: "upscale",
            label: "Upscale",
            icon: <UpscaleIcon className={GLYPH} />,
            onSelect: () => actions.upscale(asset, index),
          },
        ]),
    ...(isPromotable(asset)
      ? [
          {
            key: "promote",
            label: "Copy into a character…",
            icon: <PromoteIcon className={GLYPH} />,
            onSelect: onPromote,
          },
        ]
      : []),
    {
      key: "download",
      label: `Download ${assetLabel(asset.name)}`,
      icon: <DownloadIcon className={GLYPH} />,
      onSelect: () => void actions.download(asset),
    },
  ];

  return (
    // **The frame and the clipping are on an inner box, not on this one.** The
    // menu is a sibling of the picture and its panel is absolutely positioned
    // rather than portalled (`ItemActions` explains why), so an
    // `overflow-hidden` around both would cut the panel off at the tile's edge
    // — which is exactly what a menu opening downward out of a 150px tile does.
    <div className="group relative">
      <div className="overflow-hidden border border-line bg-card">
        {/* The tile is the opening button; its frame is on the box around it. */}
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
      </div>

      {/* Hidden until the tile is hovered or holds focus, and always drawn
          where there is no pointer to hover with — the rule `MediaTile`'s own
          menu follows. Nothing else is drawn over the picture. */}
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
}
