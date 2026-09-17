import { useEffect, useState, type RefObject } from "react";

/**
 * Whether an element at the top of the page has been scrolled off the top.
 *
 * An `IntersectionObserver` on it, with the sticky header's height taken off
 * the root so the strip under the header does not count as visible. Read
 * off `isIntersecting` alone: the observer reports at the crossing and then
 * goes quiet, so any second test on the rect — "and is it above the window
 * yet" — is true only when the page arrived there in one jump and false
 * under a wheel, where the crossing report carries a rect still a few pixels
 * inside. The element is the top of the page, so out of view IS above.
 *
 * jsdom's observer never fires, so this is `false` in tests — which is
 * right, since nothing there scrolls.
 */
export function useScrolledPast(ref: RefObject<HTMLElement | null>): boolean {
  const [past, setPast] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => setPast(entries.some((entry) => !entry.isIntersecting)),
      { rootMargin: `-${headerHeight()}px 0px 0px 0px` },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return past;
}

/** The header's height in pixels, read off `--header-h` so the two never disagree. */
function headerHeight(): number {
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--header-h");
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}
