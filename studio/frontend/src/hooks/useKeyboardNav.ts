import { useEffect } from "react";

interface Handlers {
  onPrev?: () => void;
  onNext?: () => void;
  onClose?: () => void;
  onToggleFullscreen?: () => void;
  onTogglePlay?: () => void;
}

/**
 * The viewer's keyboard contract, in one place so the lightbox and the reel
 * cannot drift apart.
 *
 * Arrow keys move in both axes — the lightbox is a horizontal filmstrip and the
 * reel is a vertical column, and a viewer that only answered one of them would
 * feel broken in the other.
 */
export function useKeyboardNav({
  onPrev,
  onNext,
  onClose,
  onToggleFullscreen,
  onTogglePlay,
}: Handlers) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      // Never swallow a keystroke meant for a text box (the code viewer's copy
      // button, a future search field).
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;

      switch (event.key) {
        case "ArrowLeft":
        case "ArrowUp":
          if (onPrev) {
            event.preventDefault();
            onPrev();
          }
          break;
        case "ArrowRight":
        case "ArrowDown":
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
  }, [onClose, onNext, onPrev, onTogglePlay, onToggleFullscreen]);
}
