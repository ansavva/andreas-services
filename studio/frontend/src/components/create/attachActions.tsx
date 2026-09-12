import type { ReactElement } from "react";

import type { AttachRef, AttachRole } from "../../context/CreateBarContext";
import type { MenuAction } from "../common/ActionMenu";
import { FrameEndIcon, StartFrameIcon, UseInPromptIcon, VideoIcon } from "../common/icons";

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
/**
 * The one thing a CLIP anywhere in the app can be to the create bar: the video
 * a model works from — the motion it copies, the clip it edits. Its own list
 * because it is drawn for videos where the three above are drawn for stills;
 * a clip attached as a frame is sent to a field that refuses it, and so is a
 * still attached as the clip.
 */
export const USE_AS_CLIP_ROLES = ["clip"] as const satisfies readonly AttachRole[];
export type UseAsRole = (typeof USE_AS_ROLES)[number] | (typeof USE_AS_CLIP_ROLES)[number];

/** The roles a file of this kind can be to the bar. Text and the rest: none. */
export function attachRolesFor(kind: string): readonly UseAsRole[] {
  if (kind === "image") return USE_AS_ROLES;
  if (kind === "video") return USE_AS_CLIP_ROLES;
  return [];
}

/** The line's word and glyph. Menu lines and rail cells read the same table. */
export const USE_AS_WORDS: Record<
  UseAsRole,
  { label: string; icon: (props: { className?: string }) => ReactElement }
> = {
  reference: { label: "Reference", icon: UseInPromptIcon },
  start: { label: "Start frame", icon: StartFrameIcon },
  end: { label: "End frame", icon: FrameEndIcon },
  clip: { label: "Clip", icon: VideoIcon },
};

/**
 * The heading the three sit under in a menu — the verb once, the role on
 * each line. The open file's row has no menu to join, so there the same
 * word is the trigger of a menu holding only these.
 */
export const USE_AS_GROUP = "Use as";

const GLYPH = "size-4 shrink-0 fill-none stroke-current stroke-[1.5]";

/**
 * The menu lines for one file: three for a picture, one for a clip, none for
 * anything else.
 *
 * `attach` is `useCreateBar().attach` — a frame or the clip switches the bar
 * to video and replaces what that role held, a reference accumulates; see
 * `holdsOne`. `kind` is the file's own, so a caller no longer gates on it: a
 * clip offered as a frame would be sent to a field that refuses it, and this
 * is where that is decided, once.
 */
export function attachActions(
  ref: AttachRef,
  attach: (ref: AttachRef, role: AttachRole) => void,
  kind: string = "image",
): MenuAction[] {
  return attachRolesFor(kind).map((role) => {
    const { label, icon: Icon } = USE_AS_WORDS[role];
    return {
      key: `use-as-${role}`,
      group: USE_AS_GROUP,
      label,
      icon: <Icon className={GLYPH} />,
      onSelect: () => attach(ref, role),
    };
  });
}
