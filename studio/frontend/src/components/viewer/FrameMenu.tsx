import type { AttachRole } from "../../context/CreateBarContext";
import { ActionMenu } from "../common/ActionMenu";
import { ImageIcon } from "../common/icons";
import { THIS_FRAME_GROUP, attachActions } from "../create/attachActions";

/**
 * `Frame`, on the player: the clip's menu where the clip is.
 *
 * The same lines the rail's `Use as…` offers for a video — `Use as · Source
 * video`, `This frame as · Reference / Start frame / End frame` — behind a
 * worded pill in the player's top chrome. **Because the rail is below the
 * video on a phone**, past the crumb, behind an unlabelled glyph: a person
 * who has just paused on the frame they want is looking at the frame, and
 * the control that takes it has to be there too, not a screen down and out
 * of sight of the player it reads the time from. Drawn on the poster as
 * well as during playback — a clip that never played is on its first frame,
 * and that is a frame worth taking.
 */
export function FrameMenu({
  file,
  onUseAs,
  onFrameAs,
}: {
  file: { id: string; url?: string | null; name: string; kind: string };
  onUseAs: (role: AttachRole) => void;
  onFrameAs: (role: AttachRole) => void;
}) {
  return (
    <ActionMenu
      label={file.name}
      triggerLabel="Use this frame…"
      word="Frame"
      overlay
      align="start"
      icon={<ImageIcon className="size-4 fill-none stroke-current stroke-[1.5]" />}
      actions={attachActions(
        { node: file.id, url: file.url, name: file.name, kind: "object" },
        (_, role) => onUseAs(role),
        file.kind,
        (_, role) => onFrameAs(role),
        THIS_FRAME_GROUP,
      )}
    />
  );
}
