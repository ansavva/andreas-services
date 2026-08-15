import { useCallback, useEffect, useState, type RefObject } from "react";

/**
 * The real Fullscreen API against a specific element.
 *
 * Tracks `fullscreenchange` rather than assuming our own calls succeeded,
 * because the user can leave fullscreen with Esc or the system chrome and never
 * touch our button — and Safari on iPhone refuses `requestFullscreen` on
 * anything but a <video>, so the promise rejects and the app must carry on
 * showing its own full-viewport overlay instead.
 */
export function useFullscreen(ref: RefObject<HTMLElement | null>) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [supported, setSupported] = useState(true);

  useEffect(() => {
    setSupported(typeof document !== "undefined" && document.fullscreenEnabled);

    const onChange = () => setIsFullscreen(document.fullscreenElement !== null);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggle = useCallback(async () => {
    const element = ref.current;
    if (!element) return;

    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await element.requestFullscreen({ navigationUI: "hide" });
      }
    } catch {
      // Rejected (iOS Safari, or a permissions policy). The overlay is already
      // full-viewport, so there is nothing to recover — just don't crash.
      setSupported(false);
    }
  }, [ref]);

  return { isFullscreen, supported, toggle };
}
