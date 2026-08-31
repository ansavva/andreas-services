import { useEffect, useState } from "react";

/**
 * Whether an element has come within a screen of the viewport.
 *
 * `rootMargin` is a full viewport height so a clip is loading by the time it is
 * scrolled to rather than starting then. Latches on: once something has been
 * seen there is no benefit to unloading it, and a `<video>` whose `src` was
 * taken away goes blank.
 *
 * Returns `true` outright when not watching, so the image path never pays for
 * an observer it does not use.
 *
 * **Lifted out of `MediaThumb` unchanged**, because it is the discipline rather
 * than the tile: withholding a video's `src` until it is near the viewport is
 * what stops sixty range requests on a folder of sixty clips, and `MediaPlayer`
 * draws its poster from the same free `preload="metadata"` frame. A second copy
 * inside the player would be the same rule maintained twice.
 */
export function useNearViewport(
  ref: React.RefObject<HTMLElement | null>,
  watch: boolean,
): boolean {
  const [near, setNear] = useState(!watch);

  useEffect(() => {
    if (!watch || near) return;
    const element = ref.current;
    if (!element) return;

    // jsdom has no IntersectionObserver, and a test that renders a grid should
    // not have to stub one to see anything.
    if (typeof IntersectionObserver === "undefined") {
      setNear(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setNear(true);
      },
      { rootMargin: "100% 0px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [near, ref, watch]);

  return near;
}
