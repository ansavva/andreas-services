import type { RunAsset, RunFeedRow } from "../../types";
import { assetLabel } from "../../utils/format";
import { DownloadIcon, PromoteIcon, RerunIcon, UpscaleIcon } from "../common/icons";
import { ActionMenu, type MenuAction } from "../common/ActionMenu";
import { attachActions } from "../create/attachActions";
import { ratioOf } from "./aspect";
import { kindOfFile } from "../../utils/media";
import { objectPath } from "../../utils/location";
import { pressInApp } from "../common/pressInApp";
import { useNavigate } from "react-router-dom";
import { Text } from "@ansavva/design-system";
import { MediaThumb } from "../media/MediaThumb";
import { isPromotable, isVideoAsset } from "./PromoteDrawer";
import { refOfOutput } from "./seed";
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
/**
 * What an output offers, in the order a person reaches for it: make something
 * from it, then take it away with you.
 *
 * **A still offers three roles and Upscale; a clip offers one role.** A
 * picture can be a reference or a frame, a clip can be the clip a model works
 * from, and each sent as the other is a field that refuses it — so
 * `attachActions` draws by kind. The upscaler takes an image. Download means
 * the same thing for both.
 *
 * **One list, two tiles.** The feed's tile and the tiles view's draw the same
 * menu off this, so a line added here is on both — the rule `useRunActions`
 * already keeps for the run's own actions.
 */
export function outputMenu(
  row: RunFeedRow,
  asset: RunAsset,
  index: number,
  actions: ReturnType<typeof useRunActions>,
  onPromote: () => void,
): MenuAction[] {
  const video = isVideoAsset(asset) || row.kind === "video";
  return [
    {
      key: "again",
      label: "Run again with this",
      icon: <RerunIcon className={GLYPH} />,
      onSelect: () => actions.outputAgain(asset, index),
    },
    ...attachActions(
      refOfOutput(row, asset, index),
      (_, role) => actions.useAs(asset, index, role),
      video ? "video" : "image",
      (_, role) => actions.frameAs(asset, index, role),
    ),
    ...(video
      ? []
      : [
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
}

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
  const navigate = useNavigate();
  // A training run's outputs are weights. There is no picture to open a
  // lightbox on, so the tile says what the file is and opens its page.
  // Named, so an output whose node is gone (no name, no url) still draws the
  // media tile's "Unavailable" rather than a file tile for nothing.
  const binary = Boolean(asset.name) && kindOfFile(asset.name ?? "", asset.content_type) === "other";
  if (binary) {
    const to = objectPath(asset.node);
    return (
      <a
        href={to}
        onClick={pressInApp(navigate, to)}
        aria-label={`Open ${label} — ${assetLabel(asset.name)}`}
        // A square beside the other outputs; at a phone width, where one output
        // fills the column, a square is 340px of dark for one filename — so
        // there it is a band. The same `md` corner as the media tile beside it
        // and as the Tiles wall's, so one run looks the same in both layouts.
        className="flex flex-col items-center justify-center gap-1 rounded-md border border-line bg-card px-2 py-8 text-center sm:aspect-square sm:py-2"
        data-output-file=""
      >
        <Text variant="caption" weight="medium">
          {/_high_noise/.test(asset.name ?? "") ? "LoRA · high noise" : /_low_noise/.test(asset.name ?? "") ? "LoRA · low noise" : /\.safetensors$/.test(asset.name ?? "") ? "LoRA" : "File"}
        </Text>
        <Text variant="caption" family="mono" tone="muted" className="w-full truncate text-[11px]">
          {assetLabel(asset.name)}
        </Text>
      </a>
    );
  }
  const menu = outputMenu(row, asset, index, actions, onPromote);

  return (
    // **The frame and the clipping are on an inner box, not on this one.** The
    // menu is a sibling of the picture and its panel is absolutely positioned
    // rather than portalled (`ItemActions` explains why), so an
    // `overflow-hidden` around both would cut the panel off at the tile's edge
    // — which is exactly what a menu opening downward out of a 150px tile does.
    <div className="group relative">
      {/* `md`, the Tiles wall's corner (`RunTiles`), so the same run reads the
          same in the feed and on the wall. */}
      <div className="overflow-hidden rounded-md border border-line bg-card">
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
            poster={asset.poster}
            duration={asset.duration}
            // **A still is drawn at its own shape; a clip at the plan's.** The
            // plan is a guess at what came back — `match_input_image` and `auto`
            // say nothing, and the kind's 3:4 fallback stood in — and a still
            // drawn into a guessed box and covered lost its head and feet to
            // the crop. A loaded `<img>` knows its size, so the box takes it:
            // no ratio, no crop. A clip keeps the plan's box because with a
            // poster it loads nothing until it plays, and an unloaded
            // `<video>` is 0px tall — and every video model here takes a
            // `W:H` the output honours.
            aspect="auto"
            ratio={video ? ratioOf(row) : undefined}
            fit={video ? "cover" : "contain"}
            // Dragged to the sheet, this is the run's output, not a bare file.
            drag={refOfOutput(row, asset, index)}
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
