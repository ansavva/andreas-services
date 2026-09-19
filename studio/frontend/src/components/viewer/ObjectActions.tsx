import { useLocation } from "react-router-dom";

import { IconButton } from "@ansavva/design-system";

import { copyLabel, useCopyToClipboard } from "../../hooks/useCopyToClipboard";
import { downloadNode } from "../../utils/download";
import { absoluteUrl } from "../../utils/location";
import type { AttachRole } from "../../context/CreateBarContext";
import type { FileEntry } from "../../types";
import { ActionMenu } from "../common/ActionMenu";
import { FavoriteButton } from "../common/FavoriteButton";
import { CopyKeyButton } from "../common/CopyKeyButton";
import { CloseIcon, DownloadIcon, LinkIcon, PencilIcon, TrashIcon } from "../common/icons";
import { THIS_FRAME_GROUP, attachActions } from "../create/attachActions";

interface Props {
  file: FileEntry;
  /**
   * Deletes the file, and arms before it fires — a `⋯` menu item on
   * `ItemActions`' arming machine, so the number of presses and the timeout
   * are one rule with every other delete.
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
  /**
   * Attach the open picture to the create bar — as a reference, a start
   * frame or an end frame, the three lines of one `Use as…` menu.
   *
   * **Absent on a clip.** Every role is a picture, so the page supplies this
   * for an image and nothing else.
   */
  onUseAs?: (role: AttachRole) => void;
  /**
   * The open CLIP's frame — the one the player is on — as any of the three;
   * see `useFrameGrab`. Video only. The caller reads the time off the player
   * when the line is pressed, which is why this takes no `at`.
   */
  onFrameAs?: (role: AttachRole) => void;
}

/**
 * Everything that can be done to the open file, in one row.
 *
 * **This is what `ViewerChrome` became, minus the overlay.** The old bar was a
 * gradient floating over the media, and every control in it was hand-rolled
 * inline for one reason: a portalled dialog is not painted while an element is
 * in native fullscreen. That constraint has gone: the header is ordinary page
 * flow now, so these are simply page controls, and **nothing about the file is
 * offered in fullscreen at all** — that view is for looking, and the player's
 * chrome there is the transport, sound, zoom and the way out. A `media`
 * variant drawn over the frame carried edit and delete into fullscreen until
 * 2026-09-16; it went with that decision. `ObjectPage` owns the drawer this
 * row's button asks for.
 *
 * **Delete is a `⋯` menu item.** That menu used to be `PageBar`'s, built by
 * `ObjectHeader` because the row lived in the bar; the row is in the details
 * column now, so it carries its own — `DeleteMenu` below, on the arming
 * machine `ItemActions` runs on.
 */
export function ObjectActions({
  file,
  onDelete,
  editing = false,
  onToggleEditing,
  onClose,
  onUseAs,
  onFrameAs,
}: Props) {
  // A text file has no heart. The favorites screen is a grid of media and the
  // API refuses anything else, so offering the control on a `prompt.json` would
  // be a button whose only outcome is a 400 — see `services/favorites.py`.
  const favoritable = file.kind === "image" || file.kind === "video";

  /**
   * The address bar, as a link. It is already the share link — `/o/<id>` with
   * whatever `?in=` the feed is scrolling through, and `ObjectPage` rewrites
   * it as the reel moves — so nothing is built here: a pasted copy of it lands
   * on this file, among these neighbours. In the `⋯` menu and not the row,
   * because the row's seven icons are what the column fits.
   */
  const { pathname, search } = useLocation();
  const link = useCopyToClipboard();

  return (
    <>
      {/*
        **`sm` throughout, which it was not before this row grew a seventh
        control.** The details column is a fixed 20rem and the position sits at
        its end, so the icons have about 267px: six at the default 44 fitted,
        seven did not, and the `⋯` wrapped onto a line of its own — one icon
        under the row it belongs to, which reads as a mistake rather than as a
        second row. At `sm` the seven measure 236 and fit.

        It also makes the row uniform for the first time. `CopyKeyButton` and
        the `⋯` were already 32 beside five 44s, so the mixed heights were
        visible here before anything was added.
      */}
      {favoritable && <FavoriteButton id={file.id} name={file.name} size="sm" />}

      <CopyKeyButton value={file.key} />

      {onToggleEditing && (
        <IconButton
          label={editing ? "Hide details" : "Edit details"}
          pressed={editing}
          size="sm"
          onClick={onToggleEditing}
        >
          <PencilIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
        </IconButton>
      )}

      <IconButton label="Download" size="sm" onClick={() => void downloadNode(file.id)}>
        <DownloadIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
      </IconButton>

      {onClose && (
        <IconButton label="Close (Esc)" size="sm" onClick={onClose}>
          <CloseIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
        </IconButton>
      )}

      {/* Last, one `⋯`, the way every tile's `⋮` is built: the `Use as` group
          first — Reference / Start frame / End frame for a picture, Source
          video and `This frame as` for a clip — then Delete, armed. It used
          to be two triggers: a `⊞` for `Use as…` beside the `⋯`, a glyph that
          appeared nowhere else in the app and read as nothing, on the one row
          a person came to for the picture. The clip's `Frame` pill on the
          player carries the same lines where the frame is. */}
      <ActionMenu
        label={file.name}
        triggerLabel="More actions"
        actions={[
          ...(onUseAs
            ? attachActions(
                { node: file.id, url: file.url, name: file.name, kind: "object" },
                (_, role) => onUseAs(role),
                file.kind,
                onFrameAs && ((_, role) => onFrameAs(role)),
                THIS_FRAME_GROUP,
              )
            : []),
          {
            key: "copy-link",
            label: copyLabel(link.status, "Copy link"),
            icon: <LinkIcon className="size-4 shrink-0 fill-none stroke-current stroke-[1.5]" />,
            keepOpen: true,
            onSelect: () => void link.copy(absoluteUrl(`${pathname}${search}`)),
          },
          ...(onDelete
            ? [
                {
                  key: "delete",
                  label: "Delete",
                  armedLabel: "Confirm — delete this file",
                  icon: (
                    <TrashIcon className="size-4 shrink-0 fill-none stroke-current stroke-[1.5]" />
                  ),
                  danger: true,
                  arm: true,
                  onSelect: onDelete,
                },
              ]
            : []),
        ]}
      />
    </>
  );
}
