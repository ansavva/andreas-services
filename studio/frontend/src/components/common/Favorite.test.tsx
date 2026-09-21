import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("../../apis/studio", () => ({
  getFavoriteIds: vi.fn(),
  addFavorite: vi.fn(),
  removeFavorite: vi.fn(),
}));

import { addFavorite, getFavoriteIds, removeFavorite } from "../../apis/studio";
import { useFavorites } from "../../hooks/useFavorites";
import { TestProviders } from "../../test-providers";
import { ActionMenu } from "./ActionMenu";
import { FavoriteMark, favoriteAction } from "./Favorite";

const ids = vi.mocked(getFavoriteIds);
const add = vi.mocked(addFavorite);
const remove = vi.mocked(removeFavorite);

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  ids.mockResolvedValue({ ids: [] });
  add.mockResolvedValue({ node: "node-1", favorite: true, favorited_at: "now" });
  remove.mockResolvedValue({ node: "node-1", favorite: false });
});

/**
 * The two halves the way a tile has them: the line in its menu, and the mark
 * on its picture. `favoriteAction` is a plain function so the tile's menu
 * builder can call it; the hook that feeds it is the caller's.
 */
function Tile() {
  const favorites = useFavorites();
  return (
    <div>
      <FavoriteMark id="node-1" />
      <ActionMenu
        label="a-frame.webp"
        actions={[favoriteAction("node-1", favorites.isFavorite("node-1"), favorites.toggle)]}
      />
    </div>
  );
}

/** Opens the menu and returns the heart's line, by whichever word it carries now. */
async function line(name: RegExp) {
  fireEvent.click(screen.getAllByRole("button", { name: "Actions for a-frame.webp" })[0]!);
  return await screen.findByRole("menuitem", { name });
}

it("says what the press will do, and marks a file already kept", async () => {
  ids.mockResolvedValue({ ids: ["node-1"] });
  render(<Tile />, { wrapper: TestProviders });

  await screen.findByTestId("favorite-mark");
  expect(await line(/favorites/)).toHaveProperty("textContent", "Remove from favorites");
});

it("marks the tile before the request answers", async () => {
  // The optimistic half, and it is not a nicety: a heart that waits on a round
  // trip reads as a press that did not register, and the second press people
  // then make undoes the first.
  let settle: (value: { node: string; favorite: true; favorited_at: string }) => void = () => {};
  add.mockReturnValue(new Promise((resolve) => { settle = resolve; }));
  render(<Tile />, { wrapper: TestProviders });
  await waitFor(() => expect(ids).toHaveBeenCalled());
  expect(screen.queryByTestId("favorite-mark")).toBeNull();

  fireEvent.click(await line(/^Add to favorites$/));

  await screen.findByTestId("favorite-mark");
  expect(add).toHaveBeenCalledWith("node-1");
  settle({ node: "node-1", favorite: true, favorited_at: "now" });
});

it("takes the mark back when the write fails", async () => {
  add.mockRejectedValue(new Error("nope"));
  render(<Tile />, { wrapper: TestProviders });
  await waitFor(() => expect(ids).toHaveBeenCalled());

  fireEvent.click(await line(/^Add to favorites$/));

  // Optimistic first, then rolled back — the only state a person can be left
  // in is one the server agreed to. The rejection lands too fast for the
  // mark to be caught up, so what is asserted is the press and the end.
  await waitFor(() => expect(add).toHaveBeenCalledWith("node-1"));
  await waitFor(() => expect(screen.queryByTestId("favorite-mark")).toBeNull());
  expect(await line(/favorites/)).toHaveProperty("textContent", "Add to favorites");
});

it("sends DELETE when it is already kept, never a toggle", async () => {
  // `POST` means favorited and `DELETE` means not. A toggle route needs both
  // ends to agree on the current state first, which two tabs break.
  ids.mockResolvedValue({ ids: ["node-1"] });
  render(<Tile />, { wrapper: TestProviders });
  await screen.findByTestId("favorite-mark");

  fireEvent.click(await line(/^Remove from favorites$/));

  await waitFor(() => expect(remove).toHaveBeenCalledWith("node-1"));
  expect(add).not.toHaveBeenCalled();
});
