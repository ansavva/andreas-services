import { ClipPlayer } from "./ClipPlayer";
import type { MediaPlayerProps } from "./playerShell";
import { StillPlayer } from "./StillPlayer";

export type { MediaPlayerControls, MediaPlayerProps } from "./playerShell";

/**
 * One image or video, played where it sits.
 *
 * **The affordance studio has never had is `close`.** Judging a cut used to
 * mean leaving the page it belongs to for a full-viewport reel; here the first
 * press mounts playback in the same box, and the close button puts the poster
 * back. Nothing navigates.
 *
 * Three sizes, one component: inline in a page column, filling the object
 * screen, and filling the fullscreen element. What changes between them is the
 * box the caller gives it — there is no `variant`, because a second layout is
 * the thing that made the lightbox and the reel drift apart.
 *
 * **Two players behind one name.** A clip is `ClipPlayer`, which is Video.js;
 * a still is `StillPlayer`, which is ours, because no video library does
 * pictures. They share the props, the box and the controls they hand up
 * (`playerShell`), so a caller never asks which it has — and a page stepping
 * from a clip to a still remounts, which is the one thing a page walking a
 * feed of clips does not do.
 */
export function MediaPlayer({ isVideo = false, ...props }: MediaPlayerProps) {
  return isVideo ? <ClipPlayer {...props} /> : <StillPlayer {...props} />;
}
