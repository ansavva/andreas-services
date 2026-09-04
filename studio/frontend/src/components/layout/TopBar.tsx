import { useState } from "react";

import { Drawer, Sidebar, iconButtonClass } from "@ansavva/design-system";

import { MenuIcon, SearchIcon } from "../common/icons";
import { SidebarContents } from "./AppSidebar";
import { CreateBarSlot } from "./CreateBarSlot";
import { HeaderSearch } from "./HeaderSearch";

/**
 * The bar across the top of every screen: the create bar, then search.
 *
 * **Full width and sticky**, beside the sidebar rather than above it — the
 * sidebar is the app's spine and runs the full height; this bar belongs to the
 * content column. `bg-bg` and not a translucent blur: the page background is
 * the token, and media scrolling under a frosted bar reads as a rendering
 * fault on a grid of dark frames.
 *
 * **72px above `md`, 56px below, and `--header-h` in `app.css` is that
 * number at both widths — exactly, not at least.** The lightbox and the
 * folder browser's sticky strip read the variable, so the header is `h` and
 * never grows: the create bar's active state, and a prompt taller than one
 * line, float over the page from inside their slot rather than pushing it.
 *
 * Below `md` the sidebar is not drawn, so this bar carries the way to it: a
 * menu button opening the same contents in a `Drawer`, and the search behind
 * an icon rather than inline — a 390px row has no room for the box.
 */
export function TopBar() {
  return (
    <header
      className="sticky top-0 z-30 flex h-[var(--header-h)] items-center gap-3 border-b
                 border-line bg-bg px-4 md:px-6"
    >
      <MobileMenu />

      <CreateBarSlot />

      {/* Hidden below `md`: a 320px box cannot share a 390px row with the
          create bar. `MobileSearch` is what stands in for it there. */}
      <HeaderSearch className="hidden w-64 shrink-0 md:block lg:w-80" />
      <MobileSearch />
    </header>
  );
}

/**
 * The sidebar's contents, in a drawer from the left, for a phone.
 *
 * Controlled rather than left to the drawer's own state, because following
 * a link has to close it: a menu that stays open over the page it just
 * navigated to is the overlay-on-overlay this shell exists to stop. Inside,
 * a `Sidebar.Root` pinned open — the package's parts need its context, and a
 * drawer is dismissed rather than collapsed, so the Toggle is off.
 */
function MobileMenu() {
  const [open, setOpen] = useState(false);

  return (
    <Drawer.Root side="left" open={open} onOpenChange={setOpen}>
      <Drawer.Trigger
        aria-label="Menu"
        title="Menu"
        className={iconButtonClass({ size: "md", className: "rounded-none md:hidden" })}
      >
        <MenuIcon />
      </Drawer.Trigger>

      <Drawer.Backdrop />
      <Drawer.Panel className="p-0">
        <Drawer.Title className="sr-only">Menu</Drawer.Title>
        {/* `style` beats the Root's own inline width, which is the only way to
            fill the panel: the package writes `width` inline and a class cannot
            outrank it. */}
        <Sidebar.Root
          collapsed={false}
          style={{ width: "100%" }}
          className="h-full border-r-0"
        >
          <SidebarContents toggle={false} onNavigate={() => setOpen(false)} />
        </Sidebar.Root>
      </Drawer.Panel>
    </Drawer.Root>
  );
}

/**
 * The one way to search below `md` — a `Drawer` rather than the inline box.
 *
 * The same `Combobox` full-width once it opens, autofocused so the keyboard is
 * already up when the panel lands.
 */
function MobileSearch() {
  return (
    <Drawer.Root side="top">
      <Drawer.Trigger
        aria-label="Search"
        title="Search"
        className={iconButtonClass({ size: "md", className: "rounded-none md:hidden" })}
      >
        <SearchIcon />
      </Drawer.Trigger>

      <Drawer.Backdrop />
      <Drawer.Panel>
        <Drawer.Title>Search</Drawer.Title>
        <HeaderSearch className="w-full" autoFocus />
      </Drawer.Panel>
    </Drawer.Root>
  );
}
