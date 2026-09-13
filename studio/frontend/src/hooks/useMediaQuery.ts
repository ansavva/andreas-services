import { useSyncExternalStore } from "react";

/**
 * Whether a CSS media query matches, live.
 *
 * For the few places a component has to be a DIFFERENT component per
 * breakpoint rather than the same one styled differently — the attach picker
 * is a floating box beside the create sheet on a desk and a full sheet over
 * it on a phone, and rendering both behind `md:hidden` would run the
 * listing twice. Everything that can be a class stays a class.
 *
 * jsdom has no `matchMedia`; that reads as the wide layout, which is what
 * every existing test was written against.
 */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (notify) => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
      const list = window.matchMedia(query);
      list.addEventListener("change", notify);
      return () => list.removeEventListener("change", notify);
    },
    () =>
      typeof window === "undefined" || typeof window.matchMedia !== "function"
        ? true
        : window.matchMedia(query).matches,
    () => true,
  );
}

/** Tailwind's `md` — the line between the phone layout and the rest. */
export const WIDE = "(min-width: 768px)";
