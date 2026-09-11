import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { FolderListing } from "../../types";
import { CreateBarProvider } from "../../context/CreateBarContext";
import { TestProviders } from "../../test-providers";

vi.mock("../../apis/studio", () => ({
  getFolder: vi.fn(),
  getTags: vi.fn().mockResolvedValue([]),
  createNode: vi.fn(),
  deleteNodes: vi.fn(),
  moveNodes: vi.fn(),
  copyNodes: vi.fn(),
  renameNode: vi.fn(),
}));

import { getFolder } from "../../apis/studio";
import { FolderTab } from "./FolderTab";

const list = vi.mocked(getFolder);

const ROOT_ID = "char-root-1";

function listing(overrides: Partial<FolderListing> = {}): FolderListing {
  return {
    prefix: "characters/jason",
    sort: "newest",
    depth: "1",
    breadcrumbs: [{ id: ROOT_ID, name: ROOT_ID, prefix: "characters/jason" }],
    folders: [
      { id: "node-ref", kind: "folder", prefix: "characters/jason/reference", name: "reference", last_modified: null },
    ],
    files: [],
    tags: {},
    ...overrides,
  };
}

/** Reports `location.search`, so a test can assert `fsort` landed in the URL. */
function SearchProbe() {
  const location = useLocation();
  return <span data-testid="search">{location.search}</span>;
}

function open(initial = "/c/char-root-1?tab=files") {
  render(
    <TestProviders>
      <MemoryRouter initialEntries={[initial]}>
        {/* The browser hands a picture to the create bar — see the tile's
            `Use as reference`. Nothing here presses it; the provider is what
            the grid needs to render at all. */}
        <CreateBarProvider>
          <FolderTab rootId={ROOT_ID} label="jason" />
        </CreateBarProvider>
        <SearchProbe />
      </MemoryRouter>
    </TestProviders>,
  );
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  list.mockResolvedValue(listing());
});

it("draws no chip row above the browser", async () => {
  open();
  await screen.findByText("reference");

  expect(screen.queryByRole("group", { name: "Folder shortcuts" })).toBeNull();
  expect(screen.queryByText("Top")).toBeNull();
});

it("draws no ← Back control, and no trail at the entity's own root", async () => {
  open();
  await screen.findByText("reference");

  expect(screen.queryByRole("button", { name: /back/i })).toBeNull();
  // **One crumb is no trail.** Inside a Files tab that crumb is the entity's
  // name, printed under a page whose title is the same name — it said nothing
  // until there is somewhere to go back to. Below a folder it is drawn: see
  // the case under this one.
  expect(screen.queryByRole("navigation", { name: "Breadcrumb" })).toBeNull();
});

it("draws the trail once there is somewhere above to go", async () => {
  list.mockResolvedValue(
    listing({
      breadcrumbs: [
        { id: ROOT_ID, name: ROOT_ID, prefix: "characters/jason" },
        { id: "node-ref", name: "reference", prefix: "characters/jason/reference" },
      ],
      folders: [],
    }),
  );
  open();

  const trail = await screen.findByRole("navigation", { name: "Breadcrumb" });
  // The boundary crumb takes the entity's label in place of the id its root
  // folder is stored under — see `boundaryLabel`.
  expect(trail.textContent).toContain("jason");
  expect(trail.textContent).toContain("reference");
});

it("sort is URL state, namespaced as fsort", async () => {
  open();
  await screen.findByText("reference");

  fireEvent.click(screen.getByRole("combobox", { name: "Sort order" }));
  fireEvent.click(await screen.findByRole("option", { name: "Name A–Z" }));

  await waitFor(() =>
    expect(screen.getByTestId("search")).toHaveProperty(
      "textContent",
      "?tab=files&fsort=name",
    ),
  );
  await waitFor(() =>
    expect(list).toHaveBeenLastCalledWith(expect.anything(), "name", expect.anything()),
  );
});
