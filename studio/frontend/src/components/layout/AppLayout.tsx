import { Outlet } from "react-router-dom";

import { AppHeader } from "./AppHeader";

/**
 * The shell every screen renders inside.
 *
 * **This replaces seven copies of the same wrapper.** Character, project, run,
 * scene and movie each carried a private `Shell` — an identical
 * `mx-auto max-w-7xl` column with an `AppHeader` at the top — and home and the
 * browser open-coded the same thing. Seven copies is seven places a change to
 * the page frame has to be repeated, and the reason they existed at all was
 * that there was nowhere above a page to put it. A layout route is that place.
 *
 * It renders the header **outside** the content column rather than inside it,
 * which is what lets the bar be full-bleed and sticky while the content stays
 * measured. Doing it the other way needs negative margins to escape the
 * column's padding, and those break the moment the padding changes.
 *
 * The contextual half of the header — the breadcrumb and a page's own actions —
 * is `PageBar`, which each page renders as its first child. It is not lifted
 * here on purpose: it belongs to the page, changes with the page's own data,
 * and hoisting it would mean every screen pushing state up into a context to
 * have it rendered back down.
 *
 * **The column is spaced on a 24px line.** `gap-6` between sections, `py-6`
 * top and bottom, and the header's own `py-3` is half of it — so a section
 * boundary always lands on the same rhythm whatever the page above it did.
 * Replicate's grid is the same number arrived at the same way (`lh` = 24px);
 * what studio takes from it is the single spacing step, not the unit.
 * Horizontal padding stays smaller than vertical on a phone, because 24px of
 * side margin on a 390px screen is 12% of the picture.
 */
export function AppLayout() {
  return (
    <div className="flex min-h-full flex-col">
      <AppHeader />
      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
