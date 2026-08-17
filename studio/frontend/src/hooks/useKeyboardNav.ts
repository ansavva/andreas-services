import { useEffect } from "react";

interface Handlers {
  /** Up — the previous item in the column. */
  onPrev?: () => void;
  /** Down — the next item in the column. */
  onNext?: () => void;
  /** Left. Seeks backward in a video; the caller maps it to `onPrev` for a still. */
  onSeekBack?: () => void;
  /** Right. Seeks forward in a video; the caller maps it to `onNext` for a still. */
  onSeekForward?: () => void;
  onClose?: () => void;
  onToggleFullscreen?: () => void;
  onTogglePlay?: () => void;
  onToggleMuted?: () => void;
}

/**
 * The reel's keyboard contract, in one place.
 *
 * **The two axes mean different things, and that is the point.** The reel is a
 * vertical column, so Up/Down move between clips — the direction the thing
 * actually scrolls. Left/Right move through *time*, which is where every video
 * player in the world puts them, and which is what makes scrubbing reachable
 * without a mouse. For a still there is no time to move through, so the caller
 * points both pairs at the same handlers and the distinction quietly vanishes.
 *
 * When this hook served a horizontal lightbox as well, both axes had to mean
 * "next item" or one of the two viewers felt broken. There is only one viewer
 * now, so the axes are free to be specific.
 */
export function useKeyboardNav({
  onPrev,
  onNext,
  onSeekBack,
  onSeekForward,
  onClose,
  onToggleFullscreen,
  onTogglePlay,
  onToggleMuted,
}: Handlers) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      // Never swallow a keystroke meant for a text box — the rename field, the
      // code viewer's copy button — or for the scrub bar, which is a range
      // input and answers the arrow keys natively. That last exclusion is what
      // lets Left/Right mean "seek" globally and "nudge the slider" while the
      // slider has focus, with no coordination between the two.
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;

      // A modified arrow is the browser's (back/forward, word jump); leave it.
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      switch (event.key) {
        case "ArrowUp":
          if (onPrev) {
            event.preventDefault();
            onPrev();
          }
          break;
        case "ArrowDown":
          if (onNext) {
            event.preventDefault();
            onNext();
          }
          break;
        case "ArrowLeft":
          if (onSeekBack) {
            event.preventDefault();
            onSeekBack();
          }
          break;
        case "ArrowRight":
          if (onSeekForward) {
            event.preventDefault();
            onSeekForward();
          }
          break;
        case "Escape":
          onClose?.();
          break;
        case "f":
        case "F":
          onToggleFullscreen?.();
          break;
        case "m":
        case "M":
          onToggleMuted?.();
          break;
        case " ":
          if (onTogglePlay) {
            event.preventDefault();
            onTogglePlay();
          }
          break;
        default:
          break;
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    onClose,
    onNext,
    onPrev,
    onSeekBack,
    onSeekForward,
    onTogglePlay,
    onToggleFullscreen,
    onToggleMuted,
  ]);
}
