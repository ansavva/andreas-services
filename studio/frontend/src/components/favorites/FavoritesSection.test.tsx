import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("../../apis/studio", () => ({
  getFavorites: vi.fn(),
  getFavoriteIds: vi.fn(),
  addFavorite: vi.fn(),
  removeFavorite: vi.fn(),
  getAsset: vi.fn(),
}));

import { getFavoriteIds, getFavorites } from "../../apis/studio";
import { TestProviders } from "../../test-providers";
import type { FavoriteEntry } from "../../types";
import { FavoritesSection } from "./FavoritesSection";

const favorites = vi.mocked(getFavorites);

function entry(n: number): FavoriteEntry {
  return {
    id: `node-${n}`,
    key: `characters/subject-a/seed/frame-${n}.webp`,
    name: `frame-${n}.webp`,
    size: 10,
    last_modified: "2026-09-01T00:00:00Z",
    kind: "image",
    content_type: "image/webp",
    url: `https://example.test/frame-${n}.webp`,
    favorited_at: "2026-09-01T00:00:00Z",
  };
}

function page(count: number, total = count, truncated = false) {
  return {
    entries: Array.from({ length: count }, (_, i) => entry(i)),
    total,
    truncated,
    next_cursor: null,
  };
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getFavoriteIds).mockResolvedValue({ ids: [] });
});

function show(variant: "preview" | "full" = "full") {
  render(
    <TestProviders>
      <MemoryRouter>
        <FavoritesSection variant={variant} />
      </MemoryRouter>
    </TestProviders>,
  );
}

it("says what would put something here, because the control is on another page", async () => {
  favorites.mockResolvedValue(page(0));
  show();

  await screen.findByText("Nothing favorited yet.");
  expect(screen.getByText(/Press the heart/)).toBeTruthy();
});

it("opens each tile into the favorites feed, not into the folder it lives in", async () => {
  favorites.mockResolvedValue(page(1));
  show();

  const link = await screen.findByRole("link", { name: "frame-0.webp" });
  // `?in=fav`. Opening a picture from here and landing in somebody's
  // `reference` folder is the teleport `ViewerSource` exists to stop.
  expect(link.getAttribute("href")).toBe("/o/node-0?in=fav");
});

it("draws no checkbox, because nothing here acts on a selection", async () => {
  favorites.mockResolvedValue(page(1));
  show();

  await screen.findByRole("link", { name: "frame-0.webp" });
  expect(screen.queryByRole("checkbox")).toBeNull();
});

it("links to the whole screen from home only when there is more than it shows", async () => {
  favorites.mockResolvedValue(page(2, 40));
  show("preview");

  const link = await screen.findByRole("link", { name: "See all" });
  expect(link.getAttribute("href")).toBe("/favorites");
});

it("offers no See all when home is already showing everything", async () => {
  favorites.mockResolvedValue(page(2, 2));
  show("preview");

  await screen.findByRole("link", { name: "frame-0.webp" });
  expect(screen.queryByRole("link", { name: "See all" })).toBeNull();
});

it("shows more by asking for a bigger page, never by appending one", async () => {
  // The paging decision this pins: one cache entry that a heart pressed
  // anywhere invalidates, rather than an accumulated array with an id to
  // splice out of it. See the component's docstring.
  favorites.mockResolvedValue(page(60, 100));
  show("full");

  const more = await screen.findByRole("button", { name: /Show more/ });
  fireEvent.click(more);

  await waitFor(() => expect(favorites).toHaveBeenLastCalledWith(undefined, 120));
});
