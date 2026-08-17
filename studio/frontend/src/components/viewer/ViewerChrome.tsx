import { Text } from "@ansavva/design-system";

import { getAsset } from "../../apis/studio";
import { formatBytes, formatDate } from "../../utils/format";
import type { FileEntry } from "../../types";
import { ConfirmDeleteButton } from "../common/ConfirmDeleteButton";
import { CopyKeyButton } from "../common/CopyKeyButton";
import { RenameButton } from "../common/RenameButton";

interface Props {
  file: FileEntry;
  position?: string;
  isFullscreen: boolean;
  fullscreenSupported: boolean;
  onToggleFullscreen: () => void;
  onClose: () => void;
  onRename?: (name: string) => Promise<unknown>;
  onDelete?: () => Promise<unknown>;
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
}: Props) {
  async function download() {
    // Signed with `response-content-disposition: attachment` server-side. A
    // plain <a download> would be ignored here, because the presigned URL is
    // cross-origin to this app.
    const asset = await getAsset(file.key, "attachment");
    window.location.assign(asset.url);
  }

  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-3 bg-gradient-to-b from-black/80 to-transparent p-3 pb-10">
      <div className="pointer-events-auto min-w-0 flex-1">
        <Text variant="body" weight="medium" className="truncate text-white">
          {file.name}
        </Text>
        <Text variant="caption" className="truncate text-white/70">
          {formatBytes(file.size)}
          {file.last_modified ? ` · ${formatDate(file.last_modified)}` : ""}
          {position ? ` · ${position}` : ""}
        </Text>
      </div>

      <div className="pointer-events-auto flex shrink-0 items-center gap-1">
        {/* Inline feedback rather than a toast, deliberately: see above. */}
        <CopyKeyButton value={file.key} tone="chrome" />

        {onRename && <RenameButton name={file.name} onRename={onRename} tone="chrome" />}

        <ChromeButton label="Download" onClick={() => void download()}>
          <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 19h16" />
        </ChromeButton>

        {fullscreenSupported && (
          <ChromeButton
            label={isFullscreen ? "Exit fullscreen (f)" : "Fullscreen (f)"}
            onClick={onToggleFullscreen}
          >
            {isFullscreen ? (
              <path d="M9 3v6H3m12-6v6h6M9 21v-6H3m12 6v-6h6" />
            ) : (
              <path d="M3 9V3h6M21 9V3h-6M3 15v6h6m12-6v6h-6" />
            )}
          </ChromeButton>
        )}

        {onDelete && (
          <ConfirmDeleteButton noun="this file" onConfirm={onDelete} tone="chrome" />
        )}

        <ChromeButton label="Close (Esc)" onClick={onClose}>
          <path d="M6 6l12 12M18 6 6 18" />
        </ChromeButton>
      </div>
    </div>
  );
}

function ChromeButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="rounded-md p-2 text-white/80 transition-colors hover:bg-white/15 hover:text-white
                 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true" className="size-5 fill-none stroke-current stroke-[1.5]">
        {children}
      </svg>
    </button>
  );
}
