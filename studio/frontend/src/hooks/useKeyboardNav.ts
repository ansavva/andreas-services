import { useEffect } from "react";

interface Handlers {
  /** Left — the previous item in the feed. */
  onPrev?: () => void;
  /** Right — the next item in the feed. */
  onNext?: () => void;
  onClose?: () => void;
  onToggleFullscreen?: () => void;
  onTogglePlay?: () => void;
  onToggleMuted?: () => void;
}

/**
 * The object screen's keyboard contract, in one place.
 *
 * **There is one axis now, and losing the second one was the point.** The reel
 * was a vertical scroll-snap column, so Up/Down moved between clips and
 * Left/Right moved through *time* — two axes because the thing had two
 * directions to have opinions about. The object screen is a page with one
 * player on it and a filmstrip of neighbours running across, so "next" has
 * exactly one meaning and it is horizontal. Left/Right are it.
 *
 * **Seeking did not move to another key, it moved to the control that owns
 * it.** The seek bar is a real `Slider`, which answers Left/Right natively
 * while it has focus, and the walk below never sees those keystrokes because it
 * ignores anything targeting an input. So Left/Right scrub while the bar is
 * focused and step between files when it is not, with nothing coordinating the
 * two — the same bargain the reel struck, minus the second axis it needed to
 * strike it.
 *
 * Space, `m` and `f` reach the player through the controls it hands back (see
 * `MediaPlayer`'s `onControlsChange`); this hook only names the keys.
 */
export function useKeyboardNav({
  onPrev,
  onNext,
  onClose,
  onToggleFullscreen,
  onTogglePlay,
  onToggleMuted,
}: Handlers) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      // Never swallow a keystroke meant for a text box — the rename field, the
      // describe panel, the code viewer's copy button — or for the seek bar,
      // which is a range input and answers the arrow keys natively.
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      // The create bar's prompt editor is a contenteditable, not an input —
      // an arrow pressed while writing a prompt moves the caret, not the run.
      if (target?.isContentEditable) return;

      // A modified arrow is the browser's (back/forward, word jump); leave it.
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      switch (event.key) {
        case "ArrowLeft":
          if (onPrev) {
            event.preventDefault();
            onPrev();
          }
          break;
        case "ArrowRight":
          if (onNext) {
            event.preventDefault();
            onNext();
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
  }, [onClose, onNext, onPrev, onTogglePlay, onToggleFullscreen, onToggleMuted]);
}
