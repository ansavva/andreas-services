import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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

/**
 * A picture picked up anywhere brings the sheet up: on the opened run and the
 * open file the role tiles are not drawn until something calls the sheet up,
 * and a drag with nowhere to land is a gesture that does nothing.
 */
it("a node drag entering the window brings up a sheet that was away", () => {
  render(
    <TestProviders>
      <MemoryRouter initialEntries={["/o/node-1"]}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/o/:nodeId" element={<p>the file</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </TestProviders>,
  );
  // The open file keeps the sheet away: only its handle is drawn.
  expect(screen.getByRole("button", { name: /Open the create panel/ })).toBeTruthy();
  expect(screen.queryByLabelText("Prompt")).toBeNull();

  // Somebody else's drag — a file from the desktop — is not ours.
  fireEvent.dragEnter(window, { dataTransfer: { types: ["Files"] } });
  expect(screen.queryByLabelText("Prompt")).toBeNull();

  fireEvent.dragEnter(window, { dataTransfer: { types: ["application/x-studio-node"] } });
  expect(screen.getByLabelText("Prompt")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /Open the create panel/ })).toBeNull();
});
