import { useCallback, useRef, useState } from "react";

import { Drawer } from "@ansavva/design-system";

import type { RunAsset } from "../../types";
import { PromotePanel } from "./PromotePanel";

/**
 * The promote form, in a drawer beside the output it is about.
 *
 * **A drawer, not an expando under the tile.** The form is read against the
 * picture it is about — is this the face to file as identity — so the output
 * has to stay on screen while it is filled in. Lifted whole from the run page
 * when that page went: the feed and the opened run both open it, and the
 * dirty-form bargain below is one thing, not two.
 *
 * A form with words in it declines a dismissal and says so rather than
 * discarding them on a stray click outside. **Nothing is refetched when it
 * succeeds** — promoting copies the output into a character and attaches the
 * copy; the run is not touched by any of it.
 */
export function PromoteDrawer({
  asset,
  runCharacters,
  onClose,
}: {
  asset: RunAsset;
  runCharacters: string[];
  onClose: () => void;
}) {
  const dirty = useRef(false);
  const [warning, setWarning] = useState(false);

  const onOpenChange = useCallback(
    (next: boolean) => {
      if (next) return;
      if (dirty.current) {
        setWarning(true);
        return;
      }
      onClose();
    },
    [onClose],
  );

  return (
    <Drawer.Root open onOpenChange={onOpenChange}>
      <Drawer.Backdrop />
      <Drawer.Panel className="w-full max-w-md overflow-y-auto">
        <PromotePanel
          asset={asset}
          runCharacters={runCharacters}
          onClose={onClose}
          onDirtyChange={(next) => {
            dirty.current = next;
            if (!next) setWarning(false);
          }}
          unsavedWarning={warning}
          onDiscard={() => {
            setWarning(false);
            onClose();
          }}
          onKeepEditing={() => setWarning(false)}
        />
      </Drawer.Panel>
    </Drawer.Root>
  );
}

/**
 * Whether this output can become a character reference.
 *
 * **Images only.** A reference is a picture every later render is checked
 * against, so a clip cannot be one — the CLI says the same thing by resolving
 * `--from-run` output nodes against its image extension set. Decided on
 * `content_type`, which the API sends off the stored row, rather than on the
 * filename: the extension is a label a rename can change and the type is what
 * was measured when the bytes landed.
 */
export function isPromotable(asset: RunAsset): boolean {
  return (asset.content_type ?? "").startsWith("image/");
}

export function isVideoAsset(asset: RunAsset): boolean {
  return (asset.content_type ?? "").startsWith("video/");
}
