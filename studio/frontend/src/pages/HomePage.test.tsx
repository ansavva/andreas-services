import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

// The two lists are their own components with their own tests; what home
// decides is which of them it stacks, and that nothing else is fetched.
vi.mock("../components/entity/EntitySections", () => ({
  CharactersSection: () => <section aria-label="Characters" />,
  ProjectsSection: () => <section aria-label="Projects" />,
}));
vi.mock("../apis/studio", () => ({
  getMedia: vi.fn(),
  listNodes: vi.fn(),
}));

import { getMedia, listNodes } from "../apis/studio";
import { TestProviders } from "../test-providers";
import { HomePage } from "./HomePage";

afterEach(cleanup);

it("is characters and projects, and walks no media", () => {
  render(
    <TestProviders>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </TestProviders>,
  );

  expect(screen.getByText("Home")).toBeTruthy();
  expect(screen.getByRole("region", { name: "Characters" })).toBeTruthy();
  expect(screen.getByRole("region", { name: "Projects" })).toBeTruthy();

  // The Recent grid is gone, and so is the walk of the whole library it cost.
  expect(screen.queryByText("Recent")).toBeNull();
  expect(screen.queryByRole("button", { name: "Browse files" })).toBeNull();
  expect(getMedia).not.toHaveBeenCalled();
  expect(listNodes).not.toHaveBeenCalled();
});
