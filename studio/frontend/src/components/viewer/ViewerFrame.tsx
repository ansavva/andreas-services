import { createContext, useContext, useEffect, useState, type HTMLAttributes } from "react";

import { useShellSidebar } from "../../context/SidebarContext";

/**
 * The frame both viewers sit in — the opened run and the open file.
 *
 * **One box, sized to the window and nothing else.** It hangs under the
 * header — and under the create sheet when one has been called up, which is
 * `--sheet-h`, published by the shell's `SheetSlot` and `0` otherwise — so
 * the picture gets every pixel between the two and nothing lands under
 * either. Below `md` it
 * is a column that scrolls — stage, rail, strip — and from `md` a row that
 * does not, with the stage taking the width. The children are the three
 * pieces in that order; the frame places them.
 *
 * **The sidebar collapses to its rail for as long as this is up**, and comes
 * back as it was on close. Through `force`, not `setCollapsed`: the latter
 * is the person's preference and writes to storage, so a reload or a closed
 * tab inside a viewer used to leave the rail collapsed on every page after.
 * The override is lifted on unmount and the stored preference stands again
 * — which is also what a toggle pressed while the viewer was up has set.
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
 *
 * **Told by the player, through `useViewerFrameLift`, not read off the DOM.**
 * The first version was `has-[[data-fullscreen=app]]:z-50` on this class
 * list, and it held in Chromium and in a current WebKit while the phone it
 * was for kept painting the header over the picture: the attribute is set
 * after mount, and older Safari does not re-run `:has()` for that. A state
 * set by the thing that knows is not a selector engine's problem.
 */

const LiftContext = createContext<(lifted: boolean) => void>(() => undefined);

/**
 * How a player tells the frame it sits in that it has taken the screen by the
 * app's route. A no-op outside a frame — a tile in a scene's cut has no frame
 * to lift, and its fullscreen box climbs past a page column on its own.
 */
export function useViewerFrameLift() {
  return useContext(LiftContext);
}
export function ViewerFrame({
  className = "",
  style,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  const { force } = useShellSidebar();
  const [lifted, setLifted] = useState(false);
  useEffect(() => {
    force(true);
    return () => force(null);
  }, [force]);

  return (
    <LiftContext.Provider value={setLifted}>
      <div
        {...rest}
        // One z-index class at a time — see `MediaPlayer`'s box for what two
        // position classes on one element cost.
        className={`fixed inset-x-0 ${lifted ? "z-50" : "z-20"} flex flex-col overflow-y-auto bg-bg md:left-16 md:flex-row md:overflow-hidden ${className}`}
        style={{
          top: "calc(var(--header-h) + var(--sheet-h, 0px))",
          height: "calc(100dvh - var(--header-h) - var(--sheet-h, 0px))",
          ...style,
        }}
      >
        {children}
      </div>
    </LiftContext.Provider>
  );
}
