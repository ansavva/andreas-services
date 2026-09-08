import { useState } from "react";

import { Dropdown, IconButton, iconButtonClass } from "@ansavva/design-system";

import { getAsset } from "../../apis/studio";
import { useArmed } from "../../hooks/useArmed";
import type { FileEntry } from "../../types";
import { ConfirmDeleteButton } from "../common/ConfirmDeleteButton";
import { FavoriteButton } from "../common/FavoriteButton";
import { CopyKeyButton } from "../common/CopyKeyButton";
import { CloseIcon, DotsIcon, DownloadIcon, PencilIcon } from "../common/icons";

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
}: Props) {
  // A text file has no heart. The favorites screen is a grid of media and the
  // API refuses anything else, so offering the control on a `prompt.json` would
  // be a button whose only outcome is a 400 — see `services/favorites.py`.
  const favoritable = file.kind === "image" || file.kind === "video";

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
      {favoritable && <FavoriteButton id={file.id} name={file.name} />}

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

      {onClose && (
        <IconButton label="Close (Esc)" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      )}

      {/* Last, and behind a menu: every other page keeps its destructive
          control off the row of things pressed on every visit. */}
      {onDelete && <DeleteMenu onDelete={onDelete} />}
    </>
  );
}

/**
 * Delete, armed in place, behind the row's own `⋯`.
 *
 * **Right-aligned, because the trigger is the last thing in the row.** A menu
 * anchored to the trigger's LEFT edge — the design system's default — grows
 * rightwards off the screen on a phone, where the row is nearly the viewport's
 * width and this is its final button. `left-auto right-0` hangs it from the
 * right edge instead, so it opens leftwards over the row it belongs to.
 * `ItemActions` right-aligns its own for the same reason.
 */
function DeleteMenu({ onDelete }: { onDelete: () => Promise<unknown> }) {
  const [open, setOpen] = useState(false);
  const destroy = useArmed({
    onFire: async () => {
      try {
        await onDelete();
      } finally {
        setOpen(false);
      }
    },
  });

  return (
    <Dropdown.Root
      open={open}
      onOpenChange={(next: boolean) => {
        setOpen(next);
        // A half-pressed delete is never left live behind a closed menu.
        if (!next) destroy.disarm();
      }}
    >
      <Dropdown.Trigger
        aria-label="More actions"
        title="More actions"
        className={iconButtonClass({ size: "sm", className: "" })}
      >
        <DotsIcon />
      </Dropdown.Trigger>
      <Dropdown.Content className="left-auto right-0">
        <Dropdown.Item
          disabled={destroy.busy}
          {...destroy.handlers}
          onClick={(event: React.MouseEvent) => {
            // Arming must not close the menu — the confirmation *is* the item.
            if (!destroy.armed) event.preventDefault();
            destroy.press();
          }}
          className={destroy.armed || destroy.busy ? "text-danger" : undefined}
        >
          <span aria-live="assertive">
            {destroy.busy
              ? "Deleting…"
              : destroy.armed
                ? "Confirm — delete this file"
                : "Delete"}
          </span>
        </Dropdown.Item>
      </Dropdown.Content>
    </Dropdown.Root>
  );
}
