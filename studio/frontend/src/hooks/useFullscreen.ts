import { useCallback, useEffect, useState, type RefObject } from "react";

/**
 * Fullscreen for an element — the browser's, or ours where the browser refuses.
 *
 * Tracks `fullscreenchange` rather than assuming our own calls succeeded,
 * because a person can leave fullscreen with Esc or the system chrome and never
 * touch our button.
 *
 * **`fallback` is the iPhone.** Safari on iOS refuses `requestFullscreen` on
 * anything but a `<video>`, so a still could not be enlarged at all there —
 * the control was simply not drawn, and a picture on a phone was whatever the
 * page had left over. It answers with an in-app expansion instead: the same
 * `isFullscreen` state, which the player draws as a fixed full-viewport box.
 * Not as good as the real thing — the browser's own chrome stays — and far
 * better than no way to enlarge a picture on the one device where the picture
 * is smallest.
 *
 * `native` says which of the two is in force, because only the fallback needs
 * the app to position anything.
 */
export function useFullscreen(ref: RefObject<HTMLElement | null>) {
  const [native, setNative] = useState(false);
  const [fallback, setFallback] = useState(false);
  /** Whether the real API is worth trying — false once it has refused once. */
  const [real, setReal] = useState(true);

  useEffect(() => {
    setReal(typeof document !== "undefined" && document.fullscreenEnabled);

    const onChange = () => setNative(document.fullscreenElement !== null);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggle = useCallback(async () => {
    const element = ref.current;
    if (!element) return;

    if (!real) {
      setFallback((current) => !current);
      return;
    }

    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await element.requestFullscreen({ navigationUI: "hide" });
      }
    } catch {
      // Rejected (iOS Safari, or a permissions policy). Stop asking, and take
      // the app's own overlay from here — including for this press.
      setReal(false);
      setFallback(true);
    }
  }, [real, ref]);

  return {
    /** Enlarged, by either route. */
    isFullscreen: native || fallback,
    /** Enlarged by the BROWSER, which positions the element itself. */
    native,
    toggle,
  };
}
