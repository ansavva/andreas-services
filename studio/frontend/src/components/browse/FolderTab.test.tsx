import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { FolderListing } from "../../types";
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
        <FolderTab rootId={ROOT_ID} label="jason" />
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

it("draws no ← Back control, only the trail", async () => {
  open();
  await screen.findByText("reference");

  expect(screen.queryByRole("button", { name: /back/i })).toBeNull();
  // The boundary crumb, real breadcrumbs — see FolderBrowser.
  expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toHaveProperty(
    "textContent",
    "jason",
  );
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
