import { IconButton } from "@ansavva/design-system";

import { getAsset } from "../../apis/studio";
import type { FileEntry } from "../../types";
import { ConfirmDeleteButton } from "../common/ConfirmDeleteButton";
import { CopyKeyButton } from "../common/CopyKeyButton";
import { CloseIcon, DownloadIcon, PencilIcon } from "../common/icons";

/** The chrome buttons all wear the same fill over a media frame — `MediaPlayer`'s. */
const CHROME_BUTTON = "text-neutral-12 hover:bg-neutral-a5 active:bg-neutral-a6";

interface Props {
  file: FileEntry;
  /**
   * `page` is Copy, Edit, Download and Close, in the page bar's `actions`.
   * `media` is the two that have to be reachable while the player owns the
   * screen, over the frame, only while it is fullscreen.
   *
   * They are not the same set on purpose. In fullscreen there is no page to
   * read, so the controls over the frame are the two that *change* the file —
   * everything else (copy the address, download it, leave) is a thing you do
   * with the page in front of you, and drawing six icons over a photograph to
   * prove otherwise is how the reel's chrome grew.
   */
  variant?: "page" | "media";
  /**
   * The media variant's own delete, arming in place over the frame.
   *
   * **The page variant no longer takes this.** Delete moved to `PageBar`'s
   * menu — `ObjectHeader` builds that item itself, with the same `useArmed`
   * machine, because a `role="menu"` may only hold menu items and
   * `ConfirmDeleteButton` renders a `<button>`. This prop stays for
   * `variant="media"`, where the fullscreen frame has no menu to hold it.
   */
  onDelete?: () => Promise<unknown>;
  /**
   * Whether the details drawer is up, and the control that opens it — absent
   * where the file cannot be written.
   *
   * **One control, because there is one surface.** This row used to carry a
   * describe toggle *and* a rename dialog: two affordances editing three fields
   * of one row, one taking over the column and one popping up over it. Nothing
   * told them apart to a reader, so they are one drawer now and this is its
   * button.
   */
  editing?: boolean;
  onToggleEditing?: () => void;
  /** Leaves the screen. Only the page header offers it; Esc does it everywhere. */
  onClose?: () => void;
}

/**
 * Everything that can be done to the open file, in one row.
 *
 * **This is what `ViewerChrome` became, minus the overlay.** The old bar was a
 * gradient floating over the media, and every control in it was hand-rolled
 * inline for one reason: a portalled dialog is not painted while an element is
 * in native fullscreen. Two of those constraints have gone in different ways —
 * the header is ordinary page flow now, so most of these are simply page
 * controls; and where a control genuinely does have to work inside fullscreen,
 * `Drawer.Root`'s `container` aims the portal at the fullscreen element instead
 * of at `<body>`. This row no longer holds either portal itself — `ObjectPage`
 * owns the drawer and aims it — so what is left here is the button that asks
 * for it.
 *
 * **Delete stays `ConfirmDeleteButton` over the media, and becomes a page bar
 * menu item everywhere else.** The two used to be the same control at two
 * sizes; they diverged once the page bar had a menu to hold one. Over the
 * frame there is no menu — `Drawer.Root`'s `container` trick reaches
 * fullscreen for the editor, but a `Dropdown` has no such seam — so the
 * `media` variant keeps the arm-in-place button it always had. The `page`
 * variant draws no delete at all; `ObjectHeader` builds that item with the
 * same arming machine `ItemActions`' menu delete runs on.
 */
export function ObjectActions({
  file,
  variant = "page",
  onDelete,
  editing = false,
  onToggleEditing,
  onClose,
}: Props) {
  async function download() {
    // Signed with `response-content-disposition: attachment` server-side. A
    // plain <a download> would be ignored here, because the presigned URL is
    // cross-origin to this app.
    const asset = await getAsset(file.id, "attachment");
    window.location.assign(asset.url);
  }

  if (variant === "media") {
    return (
      <>
        {onToggleEditing && (
          <IconButton
            label={editing ? "Hide details" : "Edit details"}
            pressed={editing}
            size="sm"
            className={CHROME_BUTTON}
            onClick={onToggleEditing}
          >
            {/* `sm` shrinks the box and not the glyph, so the icon is sized to
                match — the rename dialog's trigger did the same. */}
            <PencilIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
          </IconButton>
        )}
        {onDelete && (
          <ConfirmDeleteButton noun="this file" onConfirm={onDelete} className={CHROME_BUTTON} />
        )}
      </>
    );
  }

  return (
    <>
      <CopyKeyButton value={file.key} />

      {onToggleEditing && (
        <IconButton
          label={editing ? "Hide details" : "Edit details"}
          pressed={editing}
          onClick={onToggleEditing}
        >
          <PencilIcon />
        </IconButton>
      )}

      <IconButton label="Download" onClick={() => void download()}>
        <DownloadIcon />
      </IconButton>

      {/* Delete is `ObjectHeader`'s menu item now, not a fifth icon here. */}

      {onClose && (
        <IconButton label="Close (Esc)" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      )}
    </>
  );
}
