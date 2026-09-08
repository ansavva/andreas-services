import { useState } from "react";

import { Drawer, Sidebar, iconButtonClass } from "@ansavva/design-system";

import { MenuIcon, SearchIcon } from "../common/icons";
import { SidebarContents } from "./AppSidebar";
import { HeaderSearch } from "./HeaderSearch";

/**
 * The bar across the top of every screen: the search, and on a phone the way
 * to the sidebar.
 *
 * **48px, and nothing in it grows.** The create bar used to live here, and
 * the header was the tallest thing on the page for it; the bar is a sheet at
 * the foot of the column now, so this is the slim strip ElevenLabs draws — a
 * search box and the room around it. `--header-h` in `app.css` is this
 * number: the lightbox and the folder browser's sticky strip read it.
 *
 * **Full width and sticky**, beside the sidebar rather than above it — the
 * sidebar is the app's spine and runs the full height; this bar belongs to
 * the content column. `bg-bg` and not a translucent blur: the page background
 * is the token, and media scrolling under a frosted strip this thin reads as
 * a rendering fault.
 *
 * Below `md` the sidebar is not drawn, so this bar carries the way to it: a
 * menu button opening the same contents in a `Drawer`, and the search behind
 * an icon rather than inline.
 */
export function TopBar() {
  return (
    <header
      className="sticky top-0 z-30 flex h-[var(--header-h)] items-center gap-2 bg-bg px-3 md:px-6"
    >
      <MobileMenu />

      {/* Centred, the way ElevenLabs sets its ⌘K box. Hidden below `md`;
          `MobileSearch` stands in for it there. */}
      <HeaderSearch className="mx-auto hidden w-72 shrink-0 md:block lg:w-96" />

      <MobileSearch className="ml-auto" />
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
        className={iconButtonClass({ size: "md", className: "md:hidden" })}
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
function MobileSearch({ className = "" }: { className?: string }) {
  return (
    <Drawer.Root side="top">
      <Drawer.Trigger
        aria-label="Search"
        title="Search"
        className={iconButtonClass({ size: "md", className: `md:hidden ${className}` })}
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
