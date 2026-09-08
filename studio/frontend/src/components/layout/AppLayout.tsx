import { Outlet } from "react-router-dom";

import { CreateBarProvider } from "../../context/CreateBarContext";
import { SidebarProvider } from "../../context/SidebarContext";
import { CreateBar } from "../create/CreateBar";
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
            {/* `pointer-events-none` on the strip, back on for the panel: the
                strip spans the column so the panel can centre in it, and a
                click in the strip's margins must reach the feed under it. */}
            <div className="pointer-events-none sticky bottom-0 z-30 px-2 pb-2 md:px-6 md:pb-4">
              <div className="pointer-events-auto mx-auto w-full max-w-3xl">
                <CreateBar />
              </div>
            </div>
          </div>
        </div>
      </CreateBarProvider>
    </SidebarProvider>
  );
}
