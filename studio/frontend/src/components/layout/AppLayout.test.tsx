import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("../../apis/studio", () => ({
  getCharacters: vi.fn().mockResolvedValue([]),
  getProjects: vi.fn().mockResolvedValue([]),
  // The create bar in the top bar reads these. See `CreateBar.test.tsx`.
  getModels: vi.fn().mockResolvedValue({}),
  getProject: vi.fn().mockResolvedValue({ id: "proj-1", name: "A project", characters: [] }),
  getTemplates: vi.fn().mockResolvedValue({ blocks: {}, templates: [] }),
}));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ email: "person@example.com", logout: vi.fn() }),
}));
vi.mock("../common/LibrarySwitcher", () => ({ LibrarySwitcher: () => null }));

import { TestProviders } from "../../test-providers";
import { AppLayout } from "./AppLayout";

afterEach(cleanup);

it("draws the sidebar, the top bar and the page, in that order, and the page inside main", () => {
  render(
    <TestProviders>
      <MemoryRouter initialEntries={["/p/proj-1"]}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/p/:projectId" element={<p>the page</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </TestProviders>,
  );

  const nav = screen.getByRole("navigation", { name: "Sections" });
  const bar = screen.getByRole("banner");
  const main = screen.getByRole("main");

  expect(within(main).getByText("the page")).toBeTruthy();
  expect(nav.compareDocumentPosition(bar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(bar.compareDocumentPosition(main) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

  // Full width: the cap that used to centre the content column is gone.
  expect(main.className).not.toMatch(/max-w-/);
  expect(main.className).not.toMatch(/mx-auto/);

  // The route lights its section from inside the layout.
  expect(within(nav).getByRole("link", { name: "Projects" }).getAttribute("aria-current")).toBe(
    "page",
  );
});
