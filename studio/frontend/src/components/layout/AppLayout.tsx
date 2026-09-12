import { useEffect } from "react";
import { Outlet } from "react-router-dom";

import { CreateBarProvider, useCreateBarState } from "../../context/CreateBarContext";
import { SidebarProvider } from "../../context/SidebarContext";
import { CreateBar } from "../create/CreateBar";
import { ChevronUpIcon } from "../common/icons";
import { AppSidebar } from "./AppSidebar";
import { TopBar } from "./TopBar";

/**
 * The shell every screen renders inside: the sidebar down the left, the top
 * bar across the content column, the page under it, and the create panel at
 * the column's foot.
 *
 * **The panel is sticky to the viewport's bottom, not fixed.** Fixed would
 * need to know the sidebar's width to sit beside it; sticky takes the column's
 * own width for free, floats while the page scrolls, and — because a sticky
 * element keeps its place in the flow — lands after the last row when the
 * page is scrolled to its end, so nothing is ever under it. The column is
 * `min-h-dvh` so that on a short page the panel still sits at the bottom
 * rather than an inch under the heading.
 *
 * **Content runs full width.** A cap on the content beside a 256px rail
 * spends the width twice. The page padding is 24px, halved at the sides on a
 * phone, and the column is spaced on a 24px line — `gap-6` between sections
 * and `py-6` top and bottom.
 *
 * The contextual half of the chrome — the breadcrumb and a page's own actions —
 * is `PageBar`, which each page renders as its first child. It belongs to the
 * page, changes with the page's own data, and hoisting it would mean every
 * screen pushing state up into a context to have it rendered back down.
 *
 * `SidebarProvider` sits here rather than in `App`, because it is the shell's
 * own state: `/auth/callback` renders outside this layout and has no sidebar
 * to collapse. `CreateBarProvider` for the same reason — the panel is the
 * shell's, and the feed's actions reach it from inside the page.
 */
export function AppLayout() {
  return (
    <SidebarProvider>
      <CreateBarProvider>
        <div className="flex min-h-full">
          <AppSidebar />
          <div className="flex min-h-dvh min-w-0 flex-1 flex-col">
            <TopBar />
            <main className="flex flex-1 flex-col gap-6 px-4 py-6 md:px-6">
              <Outlet />
            </main>
            <SheetSlot />
          </div>
        </div>
      </CreateBarProvider>
    </SidebarProvider>
  );
}

/**
 * The create sheet at the column's foot — or the handle it collapses to.
 *
 * Nothing but the handle on the opened run until something calls the sheet up
 * (Edit, Rerun, Use as reference, a tile): that screen is a fixed-height
 * viewer, so a sheet drawn over it covers the filmstrip and the transport with
 * nothing able to scroll them back into view. `shown` is the context's word on
 * that and on a sheet somebody collapsed.
 *
 * **Collapsed, it is a handle rather than nothing.** It behaves like the
 * drawer it looks like: the sheet drops to a strip in the same place, the same
 * width, with a chevron pointing back up — so the thing that comes back is
 * plainly the thing that went away, and it comes back where it went. `c`
 * reaches it from the keyboard.
 *
 * `pointer-events-none` on the strip, back on for what is in it: the strip
 * spans the column so the sheet can centre in it, and a click in the strip's
 * margins must reach the feed under it.
 */
function SheetSlot() {
  const { shown, expand } = useCreateBarState();

  /**
   * `c` opens the sheet — and only when nothing is being typed into.
   *
   * The guard is `useKeyboardNav`'s, for the same reason: a bare letter is a
   * letter to a text box, and the prompt editor is a contenteditable rather
   * than an input, so the tag test alone would swallow it mid-prompt.
   */
  useEffect(() => {
    if (shown) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "c" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (target?.isContentEditable) return;
      event.preventDefault();
      expand();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [shown, expand]);

  return (
    // **No inset, in either state.** The sheet used to float as a card with a
    // gap under it, which left a stripe of feed showing beneath something that
    // is anchored to the bottom of the window — and once it is the thing a
    // handle on the edge pulls up, the gap contradicts the gesture. It is a
    // drawer: it sits on the edge, and only its top corners are rounded.
    <div className="pointer-events-none sticky bottom-0 z-30">
      <div className="pointer-events-auto mx-auto w-full max-w-3xl">
        {shown ? (
          <CreateBar />
        ) : (
          /* The sheet's own frame, as little of it as a handle needs: `bg-sheet`
             over a blur so what is left reads as the sheet pushed down rather
             than as a new control that appeared, rounded at the top only
             because it is sitting on the window's edge, and 24px tall — it is a
             handle, and the run it belongs to is behind it. The whole strip is
             the press, so the target is the width of the sheet however short it
             is drawn.

             **Taller where there is a finger, not where there is a window.**
             24px is a comfortable target for a pointer and a hard one for a
             thumb, and it is the input device that decides that — a narrow
             window on a laptop still has a mouse. `--sheet-handle-h` in
             `app.css` carries both heights, and `ViewerFrame` reads the same
             variable to stop short of this strip. */
          // eslint-disable-next-line studio/no-hand-rolled-button -- the sheet's own frame collapsed, not a control in it.
          <button
            type="button"
            aria-label="Open the create panel (c)"
            title="Open the create panel (c)"
            onClick={expand}
            className="flex h-[var(--sheet-handle-h)] w-full items-center justify-center rounded-t-lg bg-sheet
                       ring-1 ring-line backdrop-blur-xl transition-colors hover:bg-fill
                       focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
          >
            <ChevronUpIcon className="size-4 fill-none stroke-current stroke-[1.5] text-muted" />
          </button>
        )}
      </div>
    </div>
  );
}