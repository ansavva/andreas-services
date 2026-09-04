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
  setCollapsed: (collapsed: boolean) => void;
  toggle: () => void;
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
  const [collapsed, setState] = useState<boolean>(read);

  const setCollapsed = useCallback((next: boolean) => {
    write(next);
    setState(next);
  }, []);

  const toggle = useCallback(() => {
    setState((current) => {
      write(!current);
      return !current;
    });
  }, []);

  const value = useMemo<ShellSidebarValue>(
    () => ({ collapsed, setCollapsed, toggle }),
    [collapsed, setCollapsed, toggle],
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
