// Whether the sidebar is the 256px column or the 64px icon rail.
//
// **Held here rather than inside `Sidebar.Root`, because two things outside
// the sidebar need it.** The package's own `useSidebar` throws outside its
// Root — a menu button in a top bar is the case it names — and the opened-run
// screen collapses the rail when a run is opened, from a route element that is
// nowhere near the sidebar. One provider above both is what lets either reach
// it.
//
// **Mirrored into `localStorage`, wrapped.** A person who collapses the rail
// means it for the session after this one too; the write is wrapped because
// private-mode Safari throws on the accessor, and losing the preference is a
// worse app rather than a broken one — the same bargain `LibraryContext`
// makes.
//
// **Two states, because the viewer's collapse is not a preference.** The
// viewer used to call `setCollapsed(true)` — the same call as the toggle —
// and a reload or a closed tab inside it left the rail collapsed on every
// page after, with nothing the person had chosen. So the preference and an
// override are held apart: `force` sets the override and never touches
// storage, and what is drawn is the override while there is one. The
// person's own toggle still persists, and clears the override, so a rail
// expanded by hand over an open viewer stays expanded.
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/** Where the collapsed state survives a reload. `"1"` collapsed, absent expanded. */
export const SIDEBAR_STORAGE_KEY = "studio.sidebar.collapsed";

interface ShellSidebarValue {
  collapsed: boolean;
  /** The person's choice: drawn, and remembered. */
  setCollapsed: (collapsed: boolean) => void;
  toggle: () => void;
  /**
   * A transient override: drawn, never remembered. `null` lifts it and the
   * preference stands again. The viewer's, for as long as it is up.
   */
  force: (collapsed: boolean | null) => void;
}

const ShellSidebarContext = createContext<ShellSidebarValue | null>(null);

function read(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function write(collapsed: boolean): void {
  try {
    if (collapsed) window.localStorage.setItem(SIDEBAR_STORAGE_KEY, "1");
    else window.localStorage.removeItem(SIDEBAR_STORAGE_KEY);
  } catch {
    /* see `read` */
  }
}

export function SidebarProvider({ children }: { children: ReactNode }) {
  // Lazily, so the first render is already the stored state and the rail does
  // not open and then snap shut a frame later.
  const [preference, setPreference] = useState<boolean>(read);
  const [forced, setForced] = useState<boolean | null>(null);
  const collapsed = forced ?? preference;

  const setCollapsed = useCallback((next: boolean) => {
    write(next);
    setPreference(next);
    setForced(null);
  }, []);

  // Against what is DRAWN, not the stored preference: an expand pressed on
  // a forced rail must expand it.
  const toggle = useCallback(() => setCollapsed(!collapsed), [collapsed, setCollapsed]);

  const force = useCallback((next: boolean | null) => setForced(next), []);

  const value = useMemo<ShellSidebarValue>(
    () => ({ collapsed, setCollapsed, toggle, force }),
    [collapsed, setCollapsed, toggle, force],
  );

  return <ShellSidebarContext.Provider value={value}>{children}</ShellSidebarContext.Provider>;
}

/**
 * The sidebar's collapse state, from anywhere under `AppLayout`.
 *
 * Throws outside the provider rather than returning a no-op, for the reason
 * the package's own accessor does: a toggle that silently does nothing is a bug
 * whose call site looks correct.
 */
export function useShellSidebar(): ShellSidebarValue {
  const ctx = useContext(ShellSidebarContext);
  if (!ctx) throw new Error("useShellSidebar must be used inside <SidebarProvider>");
  return ctx;
}
