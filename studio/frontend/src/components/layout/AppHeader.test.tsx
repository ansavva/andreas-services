import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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

import { TestProviders } from "../../test-providers";
import { AppHeader } from "./AppHeader";

function open() {
  render(
    <TestProviders>
      <MemoryRouter>
        <AppHeader />
      </MemoryRouter>
    </TestProviders>,
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

it("offers a search control below md, where HeaderSearch's own box is hidden", () => {
  open();
  expect(screen.getByRole("button", { name: "Search" })).toBeTruthy();
});

it("Search opens a drawer holding the same combobox, autofocused", async () => {
  open();

  expect(screen.queryByRole("dialog")).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "Search" }));

  const dialog = screen.getByRole("dialog", { name: "Search" });
  const combobox = within(dialog).getByRole("combobox", {
    name: "Find a character or project",
  });
  expect(combobox).toBeTruthy();
  expect(document.activeElement).toBe(combobox);
});
