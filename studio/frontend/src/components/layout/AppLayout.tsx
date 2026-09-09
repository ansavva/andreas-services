import { useEffect } from "react";
import { Outlet } from "react-router-dom";

import { Button } from "@ansavva/design-system";

import { CreateBarProvider, useCreateBarState } from "../../context/CreateBarContext";
import { SidebarProvider } from "../../context/SidebarContext";
import { CreateBar } from "../create/CreateBar";
import { PlusIcon } from "../common/icons";
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
 * The create sheet's strip at the column's foot — or the button that brings it
 * back.
 *
 * Nothing but the button on the opened run until something calls the sheet up
 * (Edit, Rerun, Use as reference, a tile): that screen is a fixed-height
 * viewer, so a sheet drawn over it covers the filmstrip and the transport with
 * nothing able to scroll them back into view. `shown` is the context's word on
 * that and on the sheet a person has put away by hand.
 *
 * **Put away, it leaves a round button where it stood.** A dismissal with
 * nothing left behind is a control that hides the app's main action with no way
 * back, and the sheet is where every run is made. The button sits in the same
 * corner the sheet's own Send does, so the place does not move; `c` reaches it
 * from the keyboard.
 *
 * `pointer-events-none` on the strip, back on for what is in it: the strip
 * spans the column so the panel can centre in it, and a click in the strip's
 * margins must reach the feed under it.
 */
function SheetSlot() {
  const { shown, summon } = useCreateBarState();

  /**
   * `c` calls the sheet up — and only when nothing is being typed into.
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
      summon();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [shown, summon]);

  return (
    <div className="pointer-events-none sticky bottom-0 z-30 px-2 pb-2 md:px-6 md:pb-4">
      {shown ? (
        <div className="pointer-events-auto mx-auto w-full max-w-3xl">
          <CreateBar />
        </div>
      ) : (
        <div className="pointer-events-auto mx-auto flex w-full max-w-3xl justify-end">
          <Button
            aria-label="Create (c)"
            title="Create (c)"
            onClick={summon}
            className="size-11 rounded-pill p-0 shadow-[0_8px_32px_rgba(0,0,0,0.45)]"
          >
            <PlusIcon className="size-5 fill-none stroke-current stroke-2" />
          </Button>
        </div>
      )}
    </div>
  );
}
