import { Outlet } from "react-router-dom";

import { CreateBarProvider } from "../../context/CreateBarContext";
import { SidebarProvider } from "../../context/SidebarContext";
import { AppSidebar } from "./AppSidebar";
import { TopBar } from "./TopBar";

/**
 * The shell every screen renders inside: the sidebar down the left, the top
 * bar across the content column, and the page under it.
 *
 * **Content runs full width now.** It was a `mx-auto max-w-7xl` column under
 * a top nav; the sidebar took the nav, and a cap on the content beside a
 * 256px rail spends the width twice. The page padding is the mockup's 24px,
 * halved at the sides on a phone, where 24px of margin on a 390px screen is
 * 12% of the picture.
 *
 * **The column is spaced on a 24px line.** `gap-6` between sections and `py-6`
 * top and bottom, so a section boundary always lands on the same rhythm
 * whatever the page above it did.
 *
 * The contextual half of the chrome — the breadcrumb and a page's own actions —
 * is `PageBar`, which each page renders as its first child. It is not lifted
 * here on purpose: it belongs to the page, changes with the page's own data,
 * and hoisting it would mean every screen pushing state up into a context to
 * have it rendered back down.
 *
 * `SidebarProvider` sits here rather than in `App`, because it is the shell's
 * own state: `/auth/callback` renders outside this layout and has no sidebar
 * to collapse. `CreateBarProvider` for the same reason — the bar is the top
 * bar's, and the feed's actions reach it from inside the page.
 */
export function AppLayout() {
  return (
    <SidebarProvider>
      <CreateBarProvider>
        <div className="flex min-h-full">
          <AppSidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            <TopBar />
            <main className="flex flex-1 flex-col gap-6 px-4 py-6 md:px-6">
              <Outlet />
            </main>
          </div>
        </div>
      </CreateBarProvider>
    </SidebarProvider>
  );
}
