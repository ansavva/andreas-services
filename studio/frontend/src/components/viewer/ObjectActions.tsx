import { IconButton } from "@ansavva/design-system";

import { downloadNode } from "../../utils/download";
import type { FileEntry } from "../../types";
import { ActionMenu } from "../common/ActionMenu";
import { ConfirmDeleteButton } from "../common/ConfirmDeleteButton";
import { FavoriteButton } from "../common/FavoriteButton";
import { CopyKeyButton } from "../common/CopyKeyButton";
import { CloseIcon, DownloadIcon, PencilIcon, TrashIcon, UseInPromptIcon } from "../common/icons";

interface Props {
  file: FileEntry;
  /**
   * `page` is Copy, Edit, Download, Close and a `⋯` holding Delete, under the
   * file's facts in the details column. `media` is the two that have to be
   * reachable while the player owns the screen, over the frame, only while it
   * is fullscreen.
   *
   * They are not the same set on purpose. In fullscreen there is no page to
   * read, so the controls over the frame are the two that *change* the file —
   * everything else (copy the address, download it, leave) is a thing you do
   * with the page in front of you, and drawing six icons over a photograph to
   * prove otherwise is how the reel's chrome grew.
   */
  variant?: "page" | "media";
  /**
   * Deletes the file, and arms before it fires in both variants — as a `⋯`
   * menu item on the page, as `ConfirmDeleteButton` over the frame.
   *
   * **The two are the same decision drawn twice**, because a `role="menu"` may
   * only hold menu items and `ConfirmDeleteButton` renders a `<button>`, and
   * because fullscreen has no menu to hold one: a `Drawer.Root` can aim its
   * portal at the fullscreen element and a `Dropdown` has no such seam. Both
   * run `useArmed`, so the number of presses and the timeout are one rule.
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
   * Attach the open picture to the create bar as a reference.
   *
   * **Absent on a clip and in fullscreen.** A reference is a picture, so the
   * page supplies this for an image and nothing else; and the `media` variant
   * leaves it out because the sheet it attaches to is not painted while the
   * frame owns the screen — a control whose whole feedback is a tile appearing
   * somewhere you cannot see.
   */
  onUseAsReference?: () => void;
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
 * **Delete stays `ConfirmDeleteButton` over the media, and is a `⋯` menu item
 * everywhere else.** That menu used to be `PageBar`'s, built by `ObjectHeader`
 * because the row lived in the bar; the row is in the details column now, so
 * it carries its own — `DeleteMenu` below, on the arming machine `ItemActions`
 * runs on. Over the frame there is no menu at all, so the `media` variant
 * keeps the arm-in-place button it always had.
 */
export function ObjectActions({
  file,
  variant = "page",
  onDelete,
  editing = false,
  onToggleEditing,
  onClose,
  onUseAsReference,
}: Props) {
  // A text file has no heart. The favorites screen is a grid of media and the
  // API refuses anything else, so offering the control on a `prompt.json` would
  // be a button whose only outcome is a 400 — see `services/favorites.py`.
  const favoritable = file.kind === "image" || file.kind === "video";

  if (variant === "media") {
    return (
      <>
        {/* **In both variants, and it is the only control that is.** Everything
            else here splits by whether there is a page to read — copy, download
            and close are page things; edit and delete are the two that have to
            survive fullscreen. A heart is neither: it is what the person is
            doing while they look at the picture, which is exactly the moment
            the frame owns the screen. */}
        {favoritable && <FavoriteButton id={file.id} name={file.name} intent="overlay" size="sm" />}
        {onToggleEditing && (
          <IconButton
            label={editing ? "Hide details" : "Edit details"}
            pressed={editing}
            size="sm"
            intent="overlay"
            onClick={onToggleEditing}
          >
            {/* `sm` shrinks the box and not the glyph, so the icon is sized to
                match — the rename dialog's trigger did the same. */}
            <PencilIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
          </IconButton>
        )}
        {onDelete && (
          <ConfirmDeleteButton noun="this file" onConfirm={onDelete} overlay />
        )}
      </>
    );
  }

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
        visible here before anything was added. The `media` variant has always
        been `sm` for the same reason — a row of controls beside a picture is
        not the place for the touch-target default.
      */}
      {/* First, because it is the one control here that starts something rather
          than filing, fetching or leaving — the same reason it is the first of
          the still's actions in the run's rail. */}
      {onUseAsReference && (
        <IconButton label="Use as reference" size="sm" onClick={onUseAsReference}>
          <UseInPromptIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
        </IconButton>
      )}

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

      {/* Last, and behind a menu: every other page keeps its destructive
          control off the row of things pressed on every visit. `ActionMenu`
          carries the arming — the same two presses this file used to spell out
          for itself, and the same ones every other `⋯` in the app now runs on. */}
      {onDelete && (
        <ActionMenu
          label={file.name}
          triggerLabel="More actions"
          actions={[
            {
              key: "delete",
              label: "Delete",
              armedLabel: "Confirm — delete this file",
              icon: <TrashIcon className="size-4 shrink-0 fill-none stroke-current stroke-[1.5]" />,
              danger: true,
              arm: true,
              onSelect: onDelete,
            },
          ]}
        />
      )}
    </>
  );
}
