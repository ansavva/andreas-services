import type { ReactElement } from "react";

import type { AttachRef, AttachRole } from "../../context/CreateBarContext";
import type { MenuAction } from "../common/ActionMenu";
import { FrameEndIcon, StartFrameIcon, UseInPromptIcon } from "../common/icons";

/**
 * The three things a picture anywhere in the app can be to the create bar,
 * in the order the sheet's own strip draws them for a video.
 *
 * **One list, because there were five and they disagreed.** A favorite, a
 * file in a folder, an open file, a run's output in the feed and the same
 * output in the opened run each offered `Use as reference`; two of them also
 * offered a start frame; none offered an end frame — so the only way to end a
 * clip on a picture was to open the sheet's picker and walk back to a folder
 * already on screen. Every surface now offers the same three, drawn from
 * here, and `input` is not among them: it is the upscaler's one slot and
 * `Upscale` is the word for it.
 */
export const USE_AS_ROLES = ["reference", "start", "end"] as const satisfies readonly AttachRole[];
export type UseAsRole = (typeof USE_AS_ROLES)[number];

/** The line's word and glyph. Menu lines and rail cells read the same table. */
export const USE_AS_WORDS: Record<
  UseAsRole,
  { label: string; icon: (props: { className?: string }) => ReactElement }
> = {
  reference: { label: "Use as reference", icon: UseInPromptIcon },
  start: { label: "Use as start frame", icon: StartFrameIcon },
  end: { label: "Use as end frame", icon: FrameEndIcon },
};

const GLYPH = "size-4 shrink-0 fill-none stroke-current stroke-[1.5]";

/**
 * The three menu lines for one picture.
 *
 * `attach` is `useCreateBar().attach` — a frame switches the bar to video
 * and replaces what that frame held, a reference accumulates; see `holdsOne`.
 * A still only: a clip attached as any of these is sent to a field that
 * refuses it, so a caller draws these for an image and nothing else.
 */
export function attachActions(
  ref: AttachRef,
  attach: (ref: AttachRef, role: AttachRole) => void,
): MenuAction[] {
  return USE_AS_ROLES.map((role) => {
    const { label, icon: Icon } = USE_AS_WORDS[role];
    return {
      key: `use-as-${role}`,
      label,
      icon: <Icon className={GLYPH} />,
      onSelect: () => attach(ref, role),
    };
  });
}
