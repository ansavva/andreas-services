import { useEffect, useRef, type HTMLAttributes } from "react";

import { useShellSidebar } from "../../context/SidebarContext";

/**
 * The frame both viewers sit in — the opened run and the open file.
 *
 * **One box, sized to the window and nothing else.** It hangs under the
 * header and stops short of the create sheet's handle, so the picture gets
 * every pixel between the two and nothing lands under either. Below `md` it
 * is a column that scrolls — stage, rail, strip — and from `md` a row that
 * does not, with the stage taking the width. The children are the three
 * pieces in that order; the frame places them.
 *
 * **The sidebar collapses to its rail for as long as this is up**, and comes
 * back as it was on close. `setCollapsed` is stable; what was captured on the
 * first render is what comes back.
 *
 * `md:left-16` is the rail's width. The frame is `fixed`, and a fixed box
 * cannot take the column's width for free the way a sticky one can — so it
 * is told where the rail ends.
 *
 * **`z-50` while a player inside it is in the app's own fullscreen.** The
 * frame's `z-20` makes it a stacking context, so the player's fixed `z-50`
 * box is `z-50` *within the frame* and still under the header and the
 * sheet handle at `z-30` — on an iPhone, where only that fallback exists,
 * the search button sat on top of the maximised picture and took its taps.
 * The player marks the state (`data-fullscreen="app"`) and the frame lifts.
 */
export function ViewerFrame({
  className = "",
  style,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  const { collapsed, setCollapsed } = useShellSidebar();
  const restore = useRef(collapsed);
  useEffect(() => {
    const prior = restore.current;
    setCollapsed(true);
    return () => setCollapsed(prior);
  }, [setCollapsed]);

  return (
    <div
      {...rest}
      className={`fixed inset-x-0 z-20 flex flex-col overflow-y-auto bg-bg has-[[data-fullscreen=app]]:z-50 md:left-16 md:flex-row md:overflow-hidden ${className}`}
      style={{
        top: "var(--header-h)",
        height: "calc(100dvh - var(--header-h) - var(--sheet-handle-h))",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
