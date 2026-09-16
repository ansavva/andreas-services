import { useEffect, useState } from "react";

/**
 * How many pixels of the window's foot the on-screen keyboard is covering.
 *
 * **A phone's keyboard does not shrink the page.** On iOS, and on Chrome for
 * Android since 108, the layout viewport — the one `100dvh`, `fixed` and
 * `sticky` measure against — keeps its height when the keyboard comes up;
 * only the *visual* viewport shrinks, and Safari scrolls it to keep the
 * focused element in view. Anything pinned to the layout viewport's bottom
 * edge is therefore pinned under the keyboard: the create sheet, the moment
 * the prompt inside it was tapped, was exactly the thing the keyboard hid.
 *
 * `visualViewport` says where the visible part of the window really is:
 * `offsetTop + height` is its bottom edge in layout-viewport pixels, and what
 * is left below that to `innerHeight` is the keyboard. A sheet lifted by that
 * much sits on the keyboard's top edge instead of behind it.
 *
 * Zero on a desktop, zero while the keyboard is down, and zero on a browser
 * without `visualViewport` — the answer that leaves the layout untouched.
 * Listens to `scroll` as well as `resize`: with the keyboard up, iOS moves
 * the visual viewport within the layout one as the page scrolls, and the
 * inset changes with it.
 */
export function useKeyboardInset(): number {
  const [inset, setInset] = useState(0);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;

    const read = () => {
      const hidden = window.innerHeight - (viewport.offsetTop + viewport.height);
      setInset(Math.max(0, Math.round(hidden)));
    };

    viewport.addEventListener("resize", read);
    viewport.addEventListener("scroll", read);
    read();
    return () => {
      viewport.removeEventListener("resize", read);
      viewport.removeEventListener("scroll", read);
    };
  }, []);

  return inset;
}
