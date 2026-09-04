import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProjectSummary } from "../../types";

vi.mock("../../apis/studio", () => ({
  getProjects: vi.fn().mockResolvedValue([]),
}));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ email: "person@example.com", logout: vi.fn() }),
}));
// Out of scope here — see `LibrarySwitcher.test.tsx` for its own behaviour.
vi.mock("../common/LibrarySwitcher", () => ({ LibrarySwitcher: () => null }));

import { getProjects } from "../../apis/studio";
import { SIDEBAR_STORAGE_KEY, SidebarProvider } from "../../context/SidebarContext";
import { TestProviders } from "../../test-providers";
import { AppSidebar, DESTINATIONS, isDestinationActive } from "./AppSidebar";

const projects = vi.mocked(getProjects);

/** Reports the URL, so "following a link navigates" is assertable. */
function Address() {
  return <span data-testid="address">{useLocation().pathname}</span>;
}

function open(path = "/") {
  return render(
    <TestProviders>
      <MemoryRouter initialEntries={[path]}>
        <SidebarProvider>
          <AppSidebar />
          <Address />
        </SidebarProvider>
      </MemoryRouter>
    </TestProviders>,
  );
}

function project(id: string, name: string, updated: string): ProjectSummary {
  return { id, name, hero: null, counts: { runs: 0, scenes: 0, movies: 0 }, updated };
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
beforeEach(() => {
  vi.clearAllMocks();
  projects.mockResolvedValue([]);
});

describe("the sections", () => {
  it("lists the five destinations, in the mockup's order", () => {
    open();
    const nav = screen.getByRole("navigation", { name: "Sections" });
    const labels = within(nav)
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(labels).toEqual(["Home", "Characters", "Projects", "Files", "Templates"]);
  });

  it.each([
    ["/", "Home"],
    ["/characters", "Characters"],
    ["/c/char-1", "Characters"],
    ["/projects", "Projects"],
    ["/p/proj-1", "Projects"],
    ["/p/proj-1/r/run-1", "Projects"],
    ["/s/scene-1", "Projects"],
    ["/f", "Files"],
    ["/f/node-1", "Files"],
    ["/o/node-1", "Files"],
    ["/templates", "Templates"],
  ])("at %s the active item is %s", (path, label) => {
    open(path);
    const nav = screen.getByRole("navigation", { name: "Sections" });
    const current = within(nav)
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page")
      .map((link) => link.textContent);
    expect(current).toEqual([label]);
  });

  it("Home is exact: every path starts with `/`, and it must not stay lit", () => {
    const home = DESTINATIONS[0]!;
    expect(isDestinationActive("/", home)).toBe(true);
    expect(isDestinationActive("/projects", home)).toBe(false);
  });

  it("a plain click is taken by the router; the href stays for a modified one", () => {
    open("/");
    const link = screen.getByRole("link", { name: "Characters" });
    expect(link.getAttribute("href")).toBe("/characters");

    fireEvent.click(link, { metaKey: true });
    expect(screen.getByTestId("address").textContent).toBe("/");

    fireEvent.click(link);
    expect(screen.getByTestId("address").textContent).toBe("/characters");
  });
});

describe("collapsing", () => {
  it("the toggle collapses to the rail, and the choice survives a remount", () => {
    const first = open("/");
    expect(screen.getByText("Studio")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));

    // The rail: no wordmark, the items named for assistive tech only, and
    // the choice written down.
    expect(screen.queryByText("Studio")).toBeNull();
    expect(screen.getByRole("link", { name: "Projects" }).textContent).toBe("");
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe("1");

    first.unmount();
    open("/");
    expect(screen.queryByText("Studio")).toBeNull();
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeTruthy();
  });

  it("expanding clears the stored choice", () => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, "1");
    open("/");

    fireEvent.click(screen.getByRole("button", { name: "Expand sidebar" }));

    expect(screen.getByText("Studio")).toBeTruthy();
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBeNull();
  });

  it("a storage that throws loses the preference, not the sidebar", () => {
    const getItem = vi
      .spyOn(Storage.prototype, "getItem")
      .mockImplementation(() => {
        throw new Error("private mode");
      });
    open("/");
    expect(screen.getByText("Studio")).toBeTruthy();
    getItem.mockRestore();
  });
});

describe("recent projects", () => {
  it("lists the five most recently updated, newest first", async () => {
    projects.mockResolvedValue([
      project("proj-1", "One", "2026-09-01T00:00:00Z"),
      project("proj-6", "Six", "2026-09-06T00:00:00Z"),
      project("proj-3", "Three", "2026-09-03T00:00:00Z"),
      project("proj-2", "Two", "2026-09-02T00:00:00Z"),
      project("proj-5", "Five", "2026-09-05T00:00:00Z"),
      project("proj-4", "Four", "2026-09-04T00:00:00Z"),
    ]);
    open("/p/proj-4");

    const group = await screen.findByRole("group", { name: "Recent projects" });
    const names = within(group)
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(names).toEqual(["Six", "Five", "Four", "Three", "Two"]);

    // The project being looked at is lit, beside the Projects section.
    expect(within(group).getByRole("link", { name: "Four" }).getAttribute("aria-current")).toBe(
      "page",
    );
    expect(within(group).getByRole("link", { name: "Four" }).getAttribute("href")).toBe(
      "/p/proj-4",
    );
  });

  it("draws no group at all when there are no projects", async () => {
    open("/");
    await waitFor(() => expect(projects).toHaveBeenCalled());
    expect(screen.queryByRole("group", { name: "Recent projects" })).toBeNull();
  });

  it("goes with the labels when the rail is collapsed", async () => {
    projects.mockResolvedValue([project("proj-1", "One", "2026-09-01T00:00:00Z")]);
    open("/");
    await screen.findByRole("group", { name: "Recent projects" });

    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(screen.queryByRole("group", { name: "Recent projects" })).toBeNull();
  });
});

describe("the account", () => {
  it("is behind one button, named for the address, with sign-out inside", () => {
    open("/");
    const trigger = screen.getByRole("button", { name: "Account — person@example.com" });
    fireEvent.click(trigger);
    expect(screen.getByRole("menuitem", { name: "Sign out" })).toBeTruthy();
  });
});
