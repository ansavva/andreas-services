import { useRef } from "react";

import { Drawer } from "@ansavva/design-system";

import type { Attachment } from "../../context/CreateBarContext";
import { WIDE, useMediaQuery } from "../../hooks/useMediaQuery";
import { assetLabel } from "../../utils/format";
import { MenuLines, type MenuAction } from "../common/ActionMenu";
import { SheetHandle } from "../common/SheetHandle";

/**
 * An attached picture or clip, large, in a drawer — and under it what can
 * be done to it.
 *
 * **A tile is 72px, and 72px says which picture, not what is in it.** The
 * row's job is to say what the run will be handed and in what order; whether
 * the third reference is the one with the coat, or the start frame is the
 * take with the eyes open, is a look at the picture itself — so pressing a
 * tile opens it here, the way pressing an output opens the lightbox. A
 * clip plays.
 *
 * **The lines are the row's gestures as words.** Choose… is the picker on
 * the tile's role (a desk's press used to go straight there; it is one line
 * down now, and the ghost tile still goes there directly); the two moves
 * are the drag; the swap is the ⇄; Remove is the ×. On a phone they are the
 * only way a thumb can do any of those reliably; on a desk they are the
 * same list where the picture is.
 *
 * A right-hand drawer on a desk, the way `PromoteDrawer` sits beside a
 * run; a bottom sheet on a phone, with the grab strip every phone sheet
 * has. A line closes it, and so do the strip, the backdrop and Escape.
 *
 * **A plain picture, not `MediaPlayer`.** The player brings a fullscreen
 * control, and inside a drawer it did nothing — the drawer IS the large
 * view, and the screen-filling one is the lightbox on a run. A clip gets
 * the browser's own controls, which is all a preview needs.
 */
export function AttachPreview({
  attachment,
  caption,
  actions,
  onClose,
}: {
  attachment: Attachment;
  /** What the tile is to the run — `Image 2`, `Start`. */
  caption: string;
  actions: readonly MenuAction[];
  onClose: () => void;
}) {
  const wide = useMediaQuery(WIDE);
  const panel = useRef<HTMLDivElement>(null);
  const { ref, role } = attachment;
  const title = `${caption} — ${assetLabel(ref.name)}`;
  return (
    <Drawer.Root
      side={wide ? "right" : "bottom"}
      open
      onOpenChange={(next: boolean) => {
        if (!next) onClose();
      }}
    >
      <Drawer.Backdrop />
      <Drawer.Panel
        ref={panel}
        data-attach-preview=""
        className={
          wide
            ? "w-full max-w-md overflow-y-auto"
            : "max-h-[85dvh] overflow-y-auto overscroll-contain rounded-t-lg pt-0"
        }
      >
        <Drawer.Title className={wide ? "truncate" : "sr-only"}>{title}</Drawer.Title>
        {!wide && <SheetHandle panel={panel} onDismiss={onClose} />}
        {/* A box of a set height, the picture scaled into it whole. Shorter
            on a phone, so the first lines show under it before the sheet is
            scrolled: the picture is what the drawer is for, the lines are
            why the tile was pressed half the time. */}
        <div
          className={`${wide ? "h-[60dvh]" : "h-[42dvh]"} w-full shrink-0 overflow-hidden rounded-md bg-fill`}
        >
          {role === "clip" ? (
            <video
              src={ref.url ?? undefined}
              controls
              playsInline
              preload="metadata"
              className="size-full object-contain"
            />
          ) : (
            <img src={ref.url ?? undefined} alt={assetLabel(ref.name)} className="size-full object-contain" />
          )}
        </div>
        <MenuLines actions={actions} label={wide ? undefined : title} onClose={onClose} />
      </Drawer.Panel>
    </Drawer.Root>
  );
}
