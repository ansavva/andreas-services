import { Text } from "@ansavva/design-system";

import { getAsset } from "../../apis/studio";
import { formatBytes, formatDate } from "../../utils/format";
import type { FileEntry } from "../../types";
import { ConfirmDeleteButton } from "../common/ConfirmDeleteButton";
import { CopyKeyButton } from "../common/CopyKeyButton";
import { RenameButton } from "../common/RenameButton";
import {
  CloseIcon,
  DescribeIcon,
  DownloadIcon,
  FullscreenEnterIcon,
  FullscreenExitIcon,
  SoundOffIcon,
  SoundOnIcon,
} from "../common/icons";

interface Props {
  file: FileEntry;
  position?: string;
  isFullscreen: boolean;
  fullscreenSupported: boolean;
  onToggleFullscreen: () => void;
  onClose: () => void;
  onRename?: (name: string) => Promise<unknown>;
  onDelete?: () => Promise<unknown>;
  /** Present only for video. See the note on the sound button below. */
  muted?: boolean;
  onToggleMuted?: () => void;
  /** Whether the describe panel is up, and the toggle — absent where it cannot write. */
  describing?: boolean;
  onToggleDescribing?: () => void;
}

/**
 * The overlay's top bar.
 *
 * Kept translucent and out of the way: the media is the content, so the chrome
 * is a gradient rather than a solid bar, and everything it holds is either
 * navigation or a fact about the file on screen.
 *
 * Rename and delete live here rather than on the grid tiles because this is
 * where you are actually looking at the thing — you decide a frame is not worth
 * keeping while it fills the screen, not from a thumbnail. Both are inline for
 * the reason the whole file documents: this bar is often inside a fullscreen
 * element, and anything portalled to `<body>` is not painted while one is.
 */
export function ViewerChrome({
  file,
  position,
  isFullscreen,
  fullscreenSupported,
  onToggleFullscreen,
  onClose,
  onRename,
  onDelete,
  muted,
  onToggleMuted,
  describing = false,
  onToggleDescribing,
}: Props) {
  async function download() {
    // Signed with `response-content-disposition: attachment` server-side. A
    // plain <a download> would be ignored here, because the presigned URL is
    // cross-origin to this app.
    const asset = await getAsset(file.id, "attachment");
    window.location.assign(asset.url);
  }

  return (
    // `pt-[max(…)]` keeps the row clear of a notch. The page is served with
    // `viewport-fit=cover`, so without it this bar starts underneath the status
    // bar on a phone — the same class of problem that moved the sound control
    // up here in the first place.
    <div
      className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between
                 gap-3 bg-gradient-to-b from-black/80 to-transparent p-3 pb-10
                 pt-[max(0.75rem,env(safe-area-inset-top))]"
    >
      <div className="pointer-events-auto min-w-0 flex-1">
        <Text variant="body" weight="medium" className="truncate text-white">
          {file.name}
        </Text>
        <Text variant="caption" className="truncate text-white/70">
          {formatBytes(file.size)}
          {file.last_modified ? ` · ${formatDate(file.last_modified)}` : ""}
          {position ? ` · ${position}` : ""}
        </Text>
        {/* The caption, where the byte count used to be the most interesting
            thing on the bar. Truncated to one line: the whole of it is in the
            panel, and this is a header rather than a place to read prose. */}
        {file.description && (
          <Text variant="caption" className="truncate text-white/90">
            {file.description}
          </Text>
        )}
        {file.tags && file.tags.length > 0 && (
          <Text variant="caption" className="truncate text-white/60">
            {file.tags.join(" · ")}
          </Text>
        )}
      </div>

      <div className="pointer-events-auto flex shrink-0 items-center gap-1">
        {/*
          Sound lives up here, not down with the transport, and that is a
          mobile fix rather than a preference.

          The scrubber sits along the bottom edge, which on a phone is exactly
          where the browser's own toolbar sits — so in portrait the sound button
          was underneath Safari's chrome and simply could not be pressed. It
          reappeared in landscape, where that toolbar collapses, which is how the
          bug read: "there is no way to mute unless I turn the phone sideways".
          The reel's height now tracks the *dynamic* viewport so the bottom bar
          is reachable again, but sound is the one control you reach for with a
          clip already playing, so it belongs in the bar that is never covered.

          It is deliberately the leftmost button here, furthest from Close: a
          mis-tap on a control you press mid-clip should not be the one that
          ends the clip.
        */}
        {onToggleMuted && (
          <ChromeButton label={muted ? "Unmute (m)" : "Mute (m)"} onClick={onToggleMuted}>
            {muted ? <SoundOffIcon /> : <SoundOnIcon />}
          </ChromeButton>
        )}

        {/* Inline feedback rather than a toast, deliberately: see above. */}
        <CopyKeyButton value={file.key} tone="chrome" />

        {onToggleDescribing && (
          <ChromeButton
            label={describing ? "Hide details" : "Describe"}
            onClick={onToggleDescribing}
            pressed={describing}
          >
            <DescribeIcon />
          </ChromeButton>
        )}

        {onRename && <RenameButton name={file.name} onRename={onRename} tone="chrome" />}

        <ChromeButton label="Download" onClick={() => void download()}>
          <DownloadIcon />
        </ChromeButton>

        {fullscreenSupported && (
          <ChromeButton
            label={isFullscreen ? "Exit fullscreen (f)" : "Fullscreen (f)"}
            onClick={onToggleFullscreen}
          >
            {isFullscreen ? <FullscreenExitIcon /> : <FullscreenEnterIcon />}
          </ChromeButton>
        )}

        {onDelete && (
          <ConfirmDeleteButton noun="this file" onConfirm={onDelete} tone="chrome" />
        )}

        <ChromeButton label="Close (Esc)" onClick={onClose}>
          <CloseIcon />
        </ChromeButton>
      </div>
    </div>
  );
}

function ChromeButton({
  label,
  onClick,
  children,
  pressed,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  /** Set on a toggle. Absent on the buttons that only ever do a thing once. */
  pressed?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-pressed={pressed}
      title={label}
      className={`rounded-md p-2 transition-colors hover:bg-white/15 hover:text-white
                 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary
                 ${pressed ? "bg-white/20 text-white" : "text-white/80"}`}
    >
      {children}
    </button>
  );
}
