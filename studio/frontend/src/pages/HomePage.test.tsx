import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

// The three lists are their own components with their own tests; what home
// decides is which of them it stacks, in which order, and that nothing else is
// fetched.
vi.mock("../components/entity/EntitySections", () => ({
  CharactersSection: () => <section aria-label="Characters" />,
  ProjectsSection: () => <section aria-label="Projects" />,
}));
vi.mock("../components/favorites/FavoritesSection", () => ({
  FavoritesSection: ({ variant }: { variant?: string }) => (
    <section aria-label="Favorites" data-variant={variant} />
  ),
}));
vi.mock("../apis/studio", () => ({
  getMedia: vi.fn(),
  listNodes: vi.fn(),
}));

import { getMedia, listNodes } from "../apis/studio";
import { TestProviders } from "../test-providers";
import { HomePage } from "./HomePage";

afterEach(cleanup);

it("leads with favorites, then characters and projects, and walks no media", () => {
  render(
    <TestProviders>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </TestProviders>,
  );

  expect(screen.getByText("Home")).toBeTruthy();
  // The order is the assertion: what studio opens on is what this person kept.
  const sections = screen
    .getAllByRole("region")
    .map((region) => region.getAttribute("aria-label"))
    // The toast viewport is a region too, and it is the providers', not home's.
    .filter((label) => label !== "Notifications");
  expect(sections).toEqual(["Favorites", "Characters", "Projects"]);

  // Home shows the first rows and links to the rest — not the whole grid.
  expect(
    screen.getByRole("region", { name: "Favorites" }).getAttribute("data-variant"),
  ).toBe("preview");

  // The Recent grid is gone, and so is the walk of the whole library it cost.
  // A favorites grid is one query on one partition and does not bring it back.
  expect(screen.queryByText("Recent")).toBeNull();
  expect(screen.queryByRole("button", { name: "Browse files" })).toBeNull();
  expect(getMedia).not.toHaveBeenCalled();
  expect(listNodes).not.toHaveBeenCalled();
});
