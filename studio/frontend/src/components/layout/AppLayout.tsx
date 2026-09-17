import { useEffect } from "react";
import { Outlet } from "react-router-dom";

import { CreateBarProvider, useCreateBarState } from "../../context/CreateBarContext";
import { SidebarProvider } from "../../context/SidebarContext";
import { CreateBar } from "../create/CreateBar";
import { isNodeDrag } from "../create/dragRef";
import { AppSidebar } from "./AppSidebar";
import { TopBar } from "./TopBar";

/**
 * The shell every screen renders inside: the sidebar down the left, the top
 * bar across the content column, the create panel under it, and the page
 * under that.
 *
 * **The panel is in the flow, at the top of the column.** It was sticky to the
 * viewport's bottom, floating over the feed on every screen — and a sheet that
 * is always over something is always covering something. Now it sits under
 * the header like the rest of the page and scrolls away with it; once it has
 * gone, the sheet's own dock (`CreateBar`'s `AttachDock`) keeps its pictures
 * and a way back in the window's top-right corner. The column is `min-h-dvh`
 * so the sidebar's rail runs the window's height on a short page.
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
            <SheetSlot />
            <main className="flex flex-1 flex-col gap-6 px-4 py-6 md:px-6">
              <Outlet />
            </main>
          </div>
        </div>
      </CreateBarProvider>
    </SidebarProvider>
  );
}

/**
 * The create sheet under the header.
 *
 * **Always drawn, except on the opened run and the open file**, where nothing
 * is drawn until something calls the sheet up (Edit, Rerun, Use as
 * reference, a tile, `c`, a drag): that screen is a fixed-height viewer, and
 * a sheet drawn over it covers the filmstrip. `shown` is the context's word
 * on that. There is no collapsing it anywhere else any more — it sits in the
 * page's flow and scrolls away with the page, which is all the folding it
 * needs.
 *
 * **In the flow, and above the viewer.** The slot sits between the top bar and
 * `main`, so the page starts under it and scrolls it away. `z-[25]` is between
 * two neighbours: over the opened run's `ViewerFrame`, fixed at `z-20`, so a
 * sheet called up there is drawn over the viewer's top edge rather than under
 * it; and under the sticky top bar's `z-30`, so scrolling carries the sheet
 * beneath the header rather than across it.
 */
function SheetSlot() {
  const { shown, summon, raised } = useCreateBarState();

  /**
   * **Whatever loads the sheet with a prompt brings the page back to it.**
   * Edit or Rerun on a row half a page down, `c`: each loads a sheet that is
   * now at the top of the page and may be off the screen, and a prompt
   * nobody can see is not one they can read before sending. `raised` is the
   * context's count of those; the first render is not one of them. A
   * picture attached is not one either — the dock is where it lands.
   */
  useEffect(() => {
    if (raised === 0) return;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [raised]);

  /**
   * `c` calls the sheet up on the opened run — and only when nothing is
   * being typed into.
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

  /**
   * **A picture picked up anywhere brings the sheet up.** Every still in the
   * app drags its node (`dragRef`), and the only things that take the drop
   * are the sheet's role tiles — which, on the opened run and the open file,
   * are not drawn until something calls the sheet up. A drag that has
   * nowhere to land is a gesture that does nothing, so the drag is what
   * calls it up:
   * the first `dragenter` carrying our type expands the sheet, and the
   * tiles are under the pointer by the time it gets there. Read off the
   * type list, never the payload — see `isNodeDrag`.
   */
  useEffect(() => {
    if (shown) return;
    const onDragEnter = (event: DragEvent) => {
      if (isNodeDrag(event)) summon();
    };
    window.addEventListener("dragenter", onDragEnter);
    return () => window.removeEventListener("dragenter", onDragEnter);
  }, [shown, summon]);

  if (!shown) return null;
  return (
    <>
      {/* The page's own gutters — `main` is `px-4 py-6 md:px-6` — so the
          sheet lines up with the content under it and sits a line below the
          header rather than touching it. A card on the page, not a drawer
          hanging off the chrome, which is why all four corners are rounded.
          **Full width inside them**, like the content: the `max-w-3xl` it
          carried when it floated centred it over a feed; on the page it is a
          row of the page, and a row runs the column's width. */}
      <div className="relative z-[25] px-4 pt-6 md:px-6">
        <CreateBar />
      </div>
    </>
  );
}
