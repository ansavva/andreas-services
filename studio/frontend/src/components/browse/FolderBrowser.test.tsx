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
import { FolderBrowser, type BrowserNav } from "./FolderBrowser";

const list = vi.mocked(getFolder);

const FOLDER_ID = "node-folder";
const FILE_A = "node-file-a";

function listing(overrides: Partial<FolderListing> = {}): FolderListing {
  return {
    prefix: "root",
    sort: "newest",
    depth: "1",
    breadcrumbs: [{ id: FOLDER_ID, name: "root", prefix: "root" }],
    folders: [],
    files: [
      {
        id: FILE_A,
        key: "root/a.png",
        name: "a.png",
        size: 100,
        last_modified: "2026-08-01T00:00:00Z",
        kind: "image",
        content_type: "image/png",
        url: "https://example.com/a.png",
      },
    ],
    tags: {},
    ...overrides,
  };
}

/** Reports `location.search`, so a test can assert a filter landed in the URL. */
function SearchProbe() {
  const location = useLocation();
  return <span data-testid="search">{location.search}</span>;
}

function nav(over: Partial<BrowserNav> = {}): BrowserNav {
  return {
    folder: FOLDER_ID,
    sort: "newest",
    setSort: vi.fn(),
    goToFolder: vi.fn(),
    folderHref: () => "/f",
    openFile: vi.fn(),
    fileHref: () => "/o/x",
    ...over,
  };
}

function open(initial = "/f", navOverride: Partial<BrowserNav> = {}) {
  render(
    <TestProviders>
      <MemoryRouter initialEntries={[initial]}>
        <FolderBrowser nav={nav(navOverride)} />
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

it("the ⋯ menu holds this folder's own actions", async () => {
  open();
  await screen.findByText("a.png");

  fireEvent.click(screen.getByRole("button", { name: "More" }));

  expect(screen.getByRole("menuitem", { name: "New folder…" })).toBeTruthy();
  expect(screen.getByRole("menuitem", { name: "Copy path" })).toBeTruthy();
  // Nothing is selected yet, so there is something for it to select.
  expect(screen.getByRole("menuitem", { name: "Select all" })).toBeTruthy();
  expect(screen.getByRole("menuitem", { name: "Delete folder" })).toBeTruthy();
});

it("New folder… opens the inline form, from the menu", async () => {
  open();
  await screen.findByText("a.png");

  fireEvent.click(screen.getByRole("button", { name: "More" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "New folder…" }));

  expect(screen.getByRole("form", { name: "New folder" })).toBeTruthy();
});

it("the text filter is URL state, under q", async () => {
  open();
  await screen.findByText("a.png");

  fireEvent.click(screen.getByRole("button", { name: /^Filter/ }));
  fireEvent.change(screen.getByLabelText("Filter this folder"), {
    target: { value: "jason" },
  });

  await waitFor(() =>
    expect(screen.getByTestId("search")).toHaveProperty("textContent", "?q=jason"),
  );
});

it("tags arrive from the URL, and narrow the request", async () => {
  open("/f?tags=face");
  await waitFor(() =>
    expect(list).toHaveBeenCalledWith(
      expect.anything(),
      "newest",
      expect.objectContaining({ tag: ["face"] }),
    ),
  );
});

it("Clear resets q and tags together, in one write", async () => {
  // "jason" matches nothing in this folder, so the filtered-out state is what
  // proves the URL actually carried the query in — and what Clear has to undo.
  open("/f?q=jason&tags=face");
  await screen.findByText("Nothing here matches “jason”.");

  fireEvent.click(screen.getByRole("button", { name: /^Filter/ }));
  fireEvent.click(screen.getByRole("button", { name: "Clear" }));

  await waitFor(() => expect(screen.getByTestId("search")).toHaveProperty("textContent", ""));
  await screen.findByText("a.png");
  await waitFor(() =>
    expect(list).toHaveBeenLastCalledWith(
      expect.anything(),
      "newest",
      expect.objectContaining({ tag: [] }),
    ),
  );
});

it("selecting a file shows the sticky strip, announced politely", async () => {
  open();
  await screen.findByText("a.png");

  fireEvent.click(screen.getByRole("checkbox", { name: `Select ${"a.png"}` }));

  const count = await screen.findByText("1 selected");
  expect(count.getAttribute("aria-live")).toBe("polite");
  expect(screen.getByRole("button", { name: "Select all" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Select none" })).toBeTruthy();

  // The ⋯ menu no longer offers "Select all" while the strip already does.
  fireEvent.click(screen.getByRole("button", { name: "More" }));
  expect(screen.queryByRole("menuitem", { name: "Select all" })).toBeNull();
});
