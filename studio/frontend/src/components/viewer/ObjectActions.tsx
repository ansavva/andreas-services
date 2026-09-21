import { useLocation } from "react-router-dom";

import { Button } from "@ansavva/design-system";

import { copyLabel, useCopyToClipboard } from "../../hooks/useCopyToClipboard";
import { useFavorites } from "../../hooks/useFavorites";
import { downloadNode } from "../../utils/download";
import { absoluteUrl } from "../../utils/location";
import type { AttachRole } from "../../context/CreateBarContext";
import type { FileEntry } from "../../types";
import { ActionMenu, type MenuAction } from "../common/ActionMenu";
import { favoriteAction } from "../common/Favorite";
import {
  CheckIcon,
  ClipboardIcon,
  DownloadIcon,
  LinkIcon,
  PencilIcon,
  TrashIcon,
  WarningIcon,
} from "../common/icons";
import { THIS_FRAME_GROUP, attachActions } from "../create/attachActions";

const GLYPH = "size-4 shrink-0 fill-none stroke-current stroke-[1.5]";

interface Props {
  file: FileEntry;
  /**
   * Deletes the file, and arms before it fires — a `⋯` menu item on
   * `ItemActions`' arming machine, so the number of presses and the timeout
   * are one rule with every other delete.
   */
  onDelete?: () => Promise<unknown>;
  /**
   * Whether the details drawer is up, and the line that opens it — absent
   * where the file cannot be written.
   *
   * **One control, because there is one surface.** This row used to carry a
   * describe toggle *and* a rename dialog: two affordances editing three fields
   * of one row, one taking over the column and one popping up over it. Nothing
   * told them apart to a reader, so they are one drawer now and this is its
   * line.
   */
  editing?: boolean;
  onToggleEditing?: () => void;
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
 * Everything that can be done to the open file: one button and a menu.
 *
 * **The shape the opened run's row has — the money gesture filled, and a
 * `⋯` holding the rest.** Until 2026-09-21 this was a row of six icon
 * buttons and a `⋯`: heart, copy path, edit, download, close, dots — every
 * one the same size and the same grey, on the one page a person came to for
 * the picture, while the run beside it drew two words and a menu. And the
 * row's `⋯` sat where the icons left it, a third of the way across the
 * column, so its panel opened leftward past the column's edge and the
 * column — a scrolling one — clipped it. Now Download is the one thing on
 * the row, filled the way Rerun is on the run (it is what the page is
 * *for* once the picture has been looked at), and the heart, the path, the
 * details drawer, the `Use as` roles, the link and Delete are lines in the
 * menu, whose trigger sits at the row's end with the whole column to open
 * into.
 *
 * **Nothing about the file is offered in fullscreen.** That view is for
 * looking; the player's chrome there is the transport, sound, zoom and the
 * way out. `ObjectPage` owns the drawer the details line asks for.
 *
 * **Delete is a menu item, and arms.** `ActionMenu` keeps one arming line
 * open across its first press, so the second press is still a second press,
 * and Escape or a wander away disarms it — the same `useArmed` every other
 * delete runs on.
 */
export function ObjectActions({
  file,
  onDelete,
  editing = false,
  onToggleEditing,
  onUseAs,
  onFrameAs,
}: Props) {
  // A text file has no heart. The favorites screen is a grid of media and the
  // API refuses anything else, so offering the line on a `prompt.json` would
  // be a line whose only outcome is a 400 — see `services/favorites.py`.
  const favoritable = file.kind === "image" || file.kind === "video";
  const favorites = useFavorites();

  /**
   * The address bar, as a link. It is already the share link — `/o/<id>` with
   * whatever `?in=` the feed is scrolling through, and `ObjectPage` rewrites
   * it as the reel moves — so nothing is built here: a pasted copy of it lands
   * on this file, among these neighbours.
   */
  const { pathname, search } = useLocation();
  const link = useCopyToClipboard();
  // The slash-joined name path — what a `studio` command takes. It was
  // `CopyKeyButton` on the row; the line keeps that button's live label and
  // its three glyphs, so a press reads back the same way.
  const path = useCopyToClipboard();
  const PathGlyph =
    path.status === "copied" ? CheckIcon : path.status === "failed" ? WarningIcon : ClipboardIcon;

  const menu: MenuAction[] = [
    ...(onUseAs
      ? attachActions(
          { node: file.id, url: file.url, name: file.name, kind: "object" },
          (_, role) => onUseAs(role),
          file.kind,
          onFrameAs && ((_, role) => onFrameAs(role)),
          THIS_FRAME_GROUP,
        )
      : []),
    ...(favoritable ? [favoriteAction(file.id, favorites.isFavorite(file.id), favorites.toggle)] : []),
    {
      key: "copy-path",
      label: copyLabel(path.status, "Copy path"),
      icon: (
        <PathGlyph
          className={`${GLYPH} ${
            path.status === "copied" ? "stroke-success" : path.status === "failed" ? "stroke-danger" : ""
          }`}
        />
      ),
      keepOpen: true,
      onSelect: () => void path.copy(file.key),
    },
    ...(onToggleEditing
      ? [
          {
            key: "edit",
            label: editing ? "Hide details" : "Edit details",
            icon: <PencilIcon className={GLYPH} />,
            onSelect: onToggleEditing,
          },
        ]
      : []),
    {
      key: "copy-link",
      label: copyLabel(link.status, "Copy link"),
      icon: <LinkIcon className={GLYPH} />,
      keepOpen: true,
      onSelect: () => void link.copy(absoluteUrl(`${pathname}${search}`)),
    },
    ...(onDelete
      ? [
          {
            key: "delete",
            label: "Delete",
            armedLabel: "Confirm — delete this file",
            icon: <TrashIcon className={GLYPH} />,
            danger: true,
            arm: true,
            onSelect: onDelete,
          },
        ]
      : []),
  ];

  return (
    <>
      {/* Signed with `response-content-disposition: attachment` server-side
          and navigated to — `downloadNode` says why a plain `<a download>`
          would not do. `sm`, the size the run's Rerun is. */}
      <Button intent="primary" size="sm" onClick={() => void downloadNode(file.id)}>
        <DownloadIcon className={GLYPH} />
        Download
      </Button>

      <ActionMenu label={file.name} triggerLabel="More actions" actions={menu} />
    </>
  );
}
