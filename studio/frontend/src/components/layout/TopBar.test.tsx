import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("../../apis/studio", () => ({
  getCharacters: vi.fn().mockResolvedValue([]),
  getProjects: vi.fn().mockResolvedValue([]),
}));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ email: "person@example.com", logout: vi.fn() }),
}));
// Out of scope here — see `LibrarySwitcher.test.tsx` for its own behaviour.
vi.mock("../common/LibrarySwitcher", () => ({ LibrarySwitcher: () => null }));

import { SidebarProvider } from "../../context/SidebarContext";
import { TestProviders } from "../../test-providers";
import { TopBar } from "./TopBar";

function Address() {
  return <span data-testid="address">{useLocation().pathname}</span>;
}

function open() {
  render(
    <TestProviders>
      <MemoryRouter>
        <SidebarProvider>
          <TopBar />
          <Address />
        </SidebarProvider>
      </MemoryRouter>
    </TestProviders>,
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

it("leaves the create bar its place, before the search", () => {
  open();
  const header = screen.getByRole("banner");
  const slot = header.querySelector("[data-create-bar-slot]");
  expect(slot).toBeTruthy();
  const search = within(header).getAllByRole("combobox", {
    name: "Find a character or project",
  })[0]!;
  expect(slot!.compareDocumentPosition(search) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it("offers a search control below md, where HeaderSearch's own box is hidden", () => {
  open();
  expect(screen.getByRole("button", { name: "Search" })).toBeTruthy();
});

it("Search opens a drawer holding the same combobox, autofocused", () => {
  open();
  expect(screen.queryByRole("dialog")).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "Search" }));

  const dialog = screen.getByRole("dialog", { name: "Search" });
  const combobox = within(dialog).getByRole("combobox", {
    name: "Find a character or project",
  });
  expect(document.activeElement).toBe(combobox);
});

it("Menu opens the sidebar's contents in a drawer, and following a link closes it", () => {
  open();
  fireEvent.click(screen.getByRole("button", { name: "Menu" }));

  const dialog = screen.getByRole("dialog", { name: "Menu" });
  const nav = within(dialog).getByRole("navigation", { name: "Sections" });
  for (const label of ["Home", "Characters", "Projects", "Files", "Templates"]) {
    expect(within(nav).getByRole("link", { name: label })).toBeTruthy();
  }
  // A drawer is dismissed, not collapsed.
  expect(within(dialog).queryByRole("button", { name: /sidebar/ })).toBeNull();

  fireEvent.click(within(nav).getByRole("link", { name: "Characters" }));

  expect(screen.getByTestId("address").textContent).toBe("/characters");
  expect(screen.queryByRole("dialog")).toBeNull();
});
