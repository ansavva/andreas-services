import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it } from "vitest";

import {
  SIDEBAR_STORAGE_KEY,
  SidebarProvider,
  useShellSidebar,
} from "../../context/SidebarContext";
import { ViewerFrame } from "./ViewerFrame";

let sidebar: ReturnType<typeof useShellSidebar>;

/** The rail's state, read back, and the handle to drive it. */
function Probe() {
  sidebar = useShellSidebar();
  return <output data-testid="collapsed">{String(sidebar.collapsed)}</output>;
}

function draw(viewer: boolean) {
  return render(
    <SidebarProvider>
      {viewer && <ViewerFrame data-testid="frame" />}
      <Probe />
    </SidebarProvider>,
  );
}

const collapsed = () => screen.getByTestId("collapsed").textContent;

afterEach(cleanup);
beforeEach(() => window.localStorage.clear());

/**
 * The viewer's collapse is transient. It used to go through `setCollapsed`,
 * which is the toggle's call and writes the preference — so a reload inside
 * a viewer left the rail collapsed on every page after.
 */
it("collapses the rail while up without writing the preference, and lifts it on close", () => {
  const { rerender } = draw(true);
  expect(collapsed()).toBe("true");
  expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBeNull();

  rerender(
    <SidebarProvider>
      <Probe />
    </SidebarProvider>,
  );
  expect(collapsed()).toBe("false");
  expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBeNull();
});

it("a rail collapsed by hand comes back collapsed after the viewer", () => {
  window.localStorage.setItem(SIDEBAR_STORAGE_KEY, "1");
  const { rerender } = draw(true);
  expect(collapsed()).toBe("true");

  rerender(
    <SidebarProvider>
      <Probe />
    </SidebarProvider>,
  );
  expect(collapsed()).toBe("true");
  expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe("1");
});

it("the toggle over an open viewer expands the rail, and that is what persists", () => {
  draw(true);
  expect(collapsed()).toBe("true");

  act(() => sidebar.toggle());
  expect(collapsed()).toBe("false");
  expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBeNull();

  act(() => sidebar.toggle());
  expect(collapsed()).toBe("true");
  expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe("1");
});
