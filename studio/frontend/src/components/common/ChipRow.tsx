import type { ComponentPropsWithoutRef, ReactNode } from "react";

interface Props extends Omit<ComponentPropsWithoutRef<"div">, "className"> {
  children: ReactNode;
}

/**
 * A row of chips that scrolls sideways instead of wrapping.
 *
 * **Presentational only** — it sets no `role`, because its two callers carry
 * different semantics and neither wants a wrapper competing with them. The
 * folder shortcuts in `FolderBrowser` are navigation and label themselves a
 * group; the reference tag filter is a `ToggleGroup`, which is already a group
 * with pressed state. What they share is the *behaviour*, and only that:
 *
 * A wrapping row is the failure this exists to prevent. It is fine at four
 * items and three rows tall at nine, and it changes height as content it does
 * not control changes — so the grid under it moves down the screen for reasons
 * that have nothing to do with the grid. One scrolling row is a fixed shape at
 * any number of items.
 *
 * `-mx-1 px-1` so a focus ring on the first or last chip is not clipped by the
 * scroll container's own edge.
 */
export function ChipRow({ children, ...rest }: Props) {
  return (
    <div {...rest} className="-mx-1 flex snap-x gap-2 overflow-x-auto px-1 pb-1">
      {children}
    </div>
  );
}
