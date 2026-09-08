import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { PageBar } from "./PageBar";
import { CopyIcon, TrashIcon } from "../common/icons";

afterEach(cleanup);

function renderBar(props: Parameters<typeof PageBar>[0]) {
  return render(
    <MemoryRouter>
      <PageBar {...props} />
    </MemoryRouter>,
  );
}

/**
 * The crumb row is a fixed-height line whether or not it has anything in it —
 * `min-h-5` on the wrapper rather than the wrapper being absent — so a page
 * whose crumb loads a beat after the title (Object's cold-link case, the
 * project-name fetch behind `useProjectCrumb`) does not shift the title down
 * once it lands.
 */
it("holds the crumb row's height with no crumbs", () => {
  const { container } = renderBar({ title: "A project" });
  const row = container.querySelector(".min-h-5");
  expect(row).toBeTruthy();
  expect(row?.textContent).toBe("");
});

it("draws the crumbs it is given, never the current page", () => {
  renderBar({ crumbs: [{ label: "Projects", to: "/projects" }], title: "A project" });
  const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
  expect(nav.textContent).toBe("Projects");
});

it("truncates a string title rather than wrapping it", () => {
  renderBar({ title: "A very long project name that should not wrap the header" });
  const title = screen.getByText(/A very long project name/);
  expect(title.className).toContain("truncate");
});

it("draws no back arrow", () => {
  renderBar({ title: "A project" });
  expect(screen.queryByRole("button", { name: "Back" })).toBeNull();
});

it("renders the primary action and the icon actions beside the menu", () => {
  renderBar({
    title: "A project",
    primary: <button type="button">New run</button>,
    actions: <button type="button">Download</button>,
    menu: [{ label: "Duplicate", icon: <CopyIcon />, onSelect: vi.fn() }],
  });
  expect(screen.getByRole("button", { name: "New run" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Download" })).toBeTruthy();
  expect(screen.getAllByRole("button", { name: "More actions" })[0]!).toBeTruthy();
});

/**
 * A danger item is red and behind the menu, and firing it is the caller's
 * business — `onSelect` is what opens a `ConfirmDestroyDialog` the page owns,
 * not something this component pops up itself.
 */
it("marks a danger menu item and lets its onSelect open the caller's own confirm", () => {
  const onSelect = vi.fn();
  renderBar({
    title: "A character",
    menu: [{ label: "Delete", icon: <TrashIcon />, danger: true, onSelect }],
  });

  fireEvent.click(screen.getAllByRole("button", { name: "More actions" })[0]!);
  const item = screen.getByRole("menuitem", { name: "Delete" });
  expect(item.className).toContain("text-danger");

  fireEvent.click(item);
  expect(onSelect).toHaveBeenCalledTimes(1);
});

/**
 * **The arm-in-place escape hatch is gone, and nothing on a page used it.**
 * `onClick` + `itemProps` let a caller hand-roll a two-press delete inside the
 * bar's menu; every page instead opens a `ConfirmDestroyDialog` that makes you
 * type the name, which is the case above. Arming now belongs to `ActionMenu`
 * (`arm`), where a row's and a tile's delete — the ones with no dialog behind
 * them — reach it. `ActionMenu.test` covers it once for all four menus.
 */

