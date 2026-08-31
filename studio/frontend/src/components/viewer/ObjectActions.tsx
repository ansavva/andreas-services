import { IconButton } from "@ansavva/design-system";

import { getAsset } from "../../apis/studio";
import type { FileEntry } from "../../types";
import { ConfirmDeleteButton } from "../common/ConfirmDeleteButton";
import { CopyKeyButton } from "../common/CopyKeyButton";
import { CloseIcon, DescribeIcon, DownloadIcon } from "../common/icons";
import { RenameDialog } from "./RenameDialog";

/** The chrome buttons all wear the same fill over a media frame — `MediaPlayer`'s. */
const CHROME_BUTTON = "text-neutral-12 hover:bg-neutral-a5 active:bg-neutral-a6";

interface Props {
  file: FileEntry;
  /**
   * `page` is the full set, in the page header. `media` is the two that have to
   * be reachable while the player owns the screen.
   *
   * They are not the same set on purpose. In fullscreen there is no page to
   * read, so the controls over the frame are the two that *change* the file —
   * everything else (copy the address, describe it, download it, leave) is a
   * thing you do with the page in front of you, and drawing six icons over a
   * photograph to prove otherwise is how the reel's chrome grew.
   */
  variant?: "page" | "media";
  /**
   * Where a dialog opened from here paints. See `RenameDialog`'s `container`.
   *
   * Set for both variants: the page header's rename is a plain body portal, and
   * passing the player's container costs nothing while the player is inline —
   * the popup is `position: fixed` either way, so the element it is mounted
   * inside does not move it.
   */
  container?: HTMLElement | null;
  onRename?: (name: string) => Promise<unknown>;
  onDelete?: () => Promise<unknown>;
  /** Whether the describe panel is up, and the toggle — absent where it cannot write. */
  describing?: boolean;
  onToggleDescribing?: () => void;
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
 * `Dialog.Root`'s `container` aims the portal at the fullscreen element instead
 * of at `<body>`.
 *
 * **Delete did not follow rename into a dialog, and that is deliberate.**
 * `ConfirmDeleteButton` arms in place, names what it will destroy and disarms
 * on a timeout, on blur and on Escape. Only *one* of the two reasons it gives
 * for not being a modal was the fullscreen constraint; the other — that a
 * dialog in a fixed position trains a second click that lands before anyone
 * reads it — is untouched by anything here.
 */
export function ObjectActions({
  file,
  variant = "page",
  container,
  onRename,
  onDelete,
  describing = false,
  onToggleDescribing,
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
        {onRename && (
          <RenameDialog
            name={file.name}
            onRename={onRename}
            container={container ?? null}
            size="sm"
            className={CHROME_BUTTON}
          />
        )}
        {onDelete && (
          <ConfirmDeleteButton noun="this file" onConfirm={onDelete} tone="chrome" />
        )}
      </>
    );
  }

  return (
    <>
      <CopyKeyButton value={file.key} />

      {onToggleDescribing && (
        <IconButton
          label={describing ? "Hide details" : "Describe"}
          pressed={describing}
          onClick={onToggleDescribing}
        >
          <DescribeIcon />
        </IconButton>
      )}

      {onRename && (
        <RenameDialog name={file.name} onRename={onRename} container={container ?? null} />
      )}

      <IconButton label="Download" onClick={() => void download()}>
        <DownloadIcon />
      </IconButton>

      {onDelete && <ConfirmDeleteButton noun="this file" onConfirm={onDelete} />}

      {onClose && (
        <IconButton label="Close (Esc)" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      )}
    </>
  );
}
