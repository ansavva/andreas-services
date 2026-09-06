import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("../../apis/studio", () => ({
  getFavoriteIds: vi.fn(),
  addFavorite: vi.fn(),
  removeFavorite: vi.fn(),
}));

import { addFavorite, getFavoriteIds, removeFavorite } from "../../apis/studio";
import { TestProviders } from "../../test-providers";
import { FavoriteButton } from "./FavoriteButton";

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

function show(name = "a-frame.webp") {
  render(<FavoriteButton id="node-1" name={name} />, { wrapper: TestProviders });
  return screen.getByRole("button");
}

it("is one control in two states, not two controls", async () => {
  // `aria-pressed` rather than a label that flips between "Favorite" and
  // "Unfavorite": what the control is FOR does not change, and a name that
  // changed would read as two different buttons appearing in one place.
  ids.mockResolvedValue({ ids: ["node-1"] });
  const button = show();

  await waitFor(() => expect(button.getAttribute("aria-pressed")).toBe("true"));
  expect(button.getAttribute("aria-label")).toBe("Favorite a-frame.webp");
});

it("fills before the request answers", async () => {
  // The optimistic half, and it is not a nicety: a heart that waits on a round
  // trip reads as a press that did not register, and the second press people
  // then make undoes the first.
  let settle: (value: { node: string; favorite: true; favorited_at: string }) => void = () => {};
  add.mockReturnValue(new Promise((resolve) => { settle = resolve; }));

  const button = show();
  await waitFor(() => expect(button.getAttribute("aria-pressed")).toBe("false"));

  fireEvent.click(button);

  await waitFor(() => expect(button.getAttribute("aria-pressed")).toBe("true"));
  expect(add).toHaveBeenCalledWith("node-1");
  settle({ node: "node-1", favorite: true, favorited_at: "now" });
});

it("puts the heart back when the write fails", async () => {
  add.mockRejectedValue(new Error("nope"));
  const button = show();
  await waitFor(() => expect(button.getAttribute("aria-pressed")).toBe("false"));

  fireEvent.click(button);

  // Optimistic first, then rolled back — the only state a person can be left
  // in is one the server agreed to.
  await waitFor(() => expect(button.getAttribute("aria-pressed")).toBe("false"));
});

it("sends DELETE when it is already on, never a toggle", async () => {
  // `POST` means favorited and `DELETE` means not. A toggle route needs both
  // ends to agree on the current state first, which two tabs break.
  ids.mockResolvedValue({ ids: ["node-1"] });
  const button = show();
  await waitFor(() => expect(button.getAttribute("aria-pressed")).toBe("true"));

  fireEvent.click(button);

  await waitFor(() => expect(remove).toHaveBeenCalledWith("node-1"));
  expect(add).not.toHaveBeenCalled();
});
