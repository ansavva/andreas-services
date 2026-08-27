import { useCallback, useEffect, useState } from "react";

import { RenameForm, toneStyles, type RenameTone } from "./RenameForm";
import { PencilIcon } from "./icons";

interface Props {
  /** The current name, which is what the field opens pre-filled with. */
  name: string;
  /** Runs on submit. Rejecting keeps the field open with the message shown. */
  onRename: (next: string) => Promise<unknown>;
  tone?: RenameTone;
  className?: string;
}

/**
 * A pencil that becomes a `RenameForm` in place — rename with no parent state.
 *
 * This is the *viewer chrome's* form of rename, and the only caller left. The
 * browse page's rows used to use it too and no longer do: a row can give the
 * field a full line of its own, which is what makes it typeable, and to do that
 * the row has to know a rename is open. So the rows drive `RenameForm`
 * themselves and this stays for the one surface where opening in place is
 * right — the overlay's top bar, where there is no row to expand into and the
 * chrome is a fixed-height strip over the media.
 */
export function RenameButton({ name, onRename, tone = "chrome", className = "" }: Props) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);

  // Scrolling the reel onto a different clip must not leave the previous one's
  // name sitting in an open field.
  useEffect(() => setOpen(false), [name]);

  if (open) {
    return (
      <RenameForm
        name={name}
        onRename={onRename}
        onClose={close}
        tone={tone}
        className="flex-1"
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      aria-label={`Rename ${name}`}
      title={`Rename ${name}`}
      className={`shrink-0 rounded-md transition-colors ${toneStyles[tone]}
                  focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary
                  ${className}`}
    >
      <PencilIcon />
    </button>
  );
}
