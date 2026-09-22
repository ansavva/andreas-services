import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { FileEntry, MediaListing } from "../../types";
import { TestProviders } from "../../test-providers";

// The favorites the "server" holds for the test — a write and the re-read
// `useFavorites` makes after it have to agree, or the mark the press leaves
// is taken back by the refetch.
let held: string[] = [];

vi.mock("../../apis/studio", () => ({
  getMedia: vi.fn(),
  getAsset: vi.fn(),
  getFavoriteIds: vi.fn(async () => ({ ids: held })),
  addFavorite: vi.fn(async (id: string) => {
    held = [id, ...held.filter((each) => each !== id)];
    return { node: id };
  }),
  removeFavorite: vi.fn(async (id: string) => {
    held = held.filter((each) => each !== id);
    return { node: id };
  }),
}));

import { addFavorite, getMedia } from "../../apis/studio";
import { ProjectReel } from "./ProjectReel";
import { recallPosition, rememberPosition } from "./reelPosition";

const media = vi.mocked(getMedia);
const favorite = vi.mocked(addFavorite);

const PROJECT = "proj-0001";
const ROOT = "node-root";

function file(n: number, kind: "image" | "video" = "image"): FileEntry {
  return {
    id: `node-${n}`,
    key: `p/runs/${n}.webp`,
    name: `${n}.webp`,
    size: 1,
    last_modified: null,
    created: `2026-09-0${n}T00:00:00Z`,
    kind,
    content_type: kind === "video" ? "video/mp4" : "image/webp",
    url: `https://signed/${n}`,
  };
}

function page(items: FileEntry[], next_cursor: string | null = null): MediaListing {
  return { prefix: "", sort: "oldest", tags: {}, items, total: items.length, truncated: false, next_cursor };
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  held = [];
  window.localStorage.clear();
  // jsdom has no media pipeline: `play` logs "not implemented" and returns
  // nothing. Stubbed so a clip pane can be exercised without the noise.
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockReturnValue(undefined);
});

function open(onClose = vi.fn()) {
  render(<ProjectReel projectId={PROJECT} rootId={ROOT} name="A project" onClose={onClose} />, {
    wrapper: TestProviders,
  });
  return onClose;
}

it("walks the project's root oldest first and opens on the first item", async () => {
  media.mockResolvedValue(page([file(1), file(2), file(3)]));
  open();

  expect(await screen.findByText("1 of 3")).toBeTruthy();
  expect(media).toHaveBeenCalledWith({ node: ROOT }, "oldest", undefined);
  expect(screen.getByText("1.webp")).toBeTruthy();
  // The first item is remembered as soon as it is the one on screen.
  await waitFor(() => expect(recallPosition(PROJECT)).toBe("node-1"));
});

it("opens where it was left", async () => {
  media.mockResolvedValue(page([file(1), file(2), file(3)]));
  rememberPosition(PROJECT, "node-2");
  open();

  expect(await screen.findByText("2 of 3")).toBeTruthy();
  expect(screen.getByText("2.webp")).toBeTruthy();
});

/**
 * The remembered item may be past the first page — the walk pages forward
 * until it is found rather than opening at the top and calling it close.
 */
it("pages forward to a remembered item on a later page", async () => {
  media
    .mockResolvedValueOnce(page([file(1), file(2)], "2"))
    .mockResolvedValueOnce(page([file(3), file(4)]));
  rememberPosition(PROJECT, "node-3");
  open();

  expect(await screen.findByText("3 of 4")).toBeTruthy();
  expect(media).toHaveBeenCalledTimes(2);
  expect(media).toHaveBeenLastCalledWith({ node: ROOT }, "oldest", "2");
});

it("starts over when the remembered item is gone", async () => {
  media.mockResolvedValue(page([file(1), file(2)]));
  rememberPosition(PROJECT, "node-deleted");
  open();

  expect(await screen.findByText("1 of 2")).toBeTruthy();
  await waitFor(() => expect(recallPosition(PROJECT)).toBe("node-1"));
});

/**
 * The end forgets the place: a reel left on its last item opens at the
 * start next time, and says so with the way back now.
 */
it("forgets the place at the end and offers Start over", async () => {
  media.mockResolvedValue(page([file(1), file(2)]));
  rememberPosition(PROJECT, "node-2");
  open();

  expect(await screen.findByText("2 of 2")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Start over" })).toBeTruthy();
  await waitFor(() => expect(recallPosition(PROJECT)).toBeNull());
});

it("a double tap hearts the item on screen, and never un-hearts it", async () => {
  media.mockResolvedValue(page([file(1)]));
  open();
  await screen.findByText("1 of 1");

  const pane = screen.getByTestId("reel-pane");
  const tap = () => {
    fireEvent.pointerDown(pane, { pointerId: 1, isPrimary: true, clientX: 50, clientY: 80 });
    fireEvent.pointerUp(pane, { pointerId: 1, isPrimary: true, clientX: 0, clientY: 0 });
  };
  // Two taps back to back are well inside `DOUBLE_TAP_MS` on any clock.
  const doubleTap = () =>
    act(async () => {
      tap();
      tap();
    });

  await doubleTap();
  expect(favorite).toHaveBeenCalledWith("node-1");
  expect(screen.getByTestId("heart-burst")).toBeTruthy();
  // The mark is the state the press leaves; it is on before the round trip.
  await waitFor(() => expect(screen.getByTestId("reel-favorited")).toBeTruthy());

  await doubleTap();
  expect(favorite).toHaveBeenCalledTimes(2);
  expect(favorite).toHaveBeenLastCalledWith("node-1");
  expect(screen.getByTestId("reel-favorited")).toBeTruthy();
});

it("Escape closes it", async () => {
  media.mockResolvedValue(page([file(1)]));
  const onClose = open();
  await screen.findByText("1 of 1");

  fireEvent.keyDown(window, { key: "Escape" });
  expect(onClose).toHaveBeenCalledTimes(1);
});

it("offers sound only on a clip", async () => {
  media.mockResolvedValue(page([file(1, "video")]));
  open();
  await screen.findByText("1 of 1");

  const unmute = screen.getByRole("button", { name: "Unmute (m)" });
  fireEvent.click(unmute);
  expect(screen.getByRole("button", { name: "Mute (m)" })).toBeTruthy();
  expect((document.querySelector("video") as HTMLVideoElement).muted).toBe(false);
});

it("says so when the project holds nothing to play", async () => {
  media.mockResolvedValue(page([]));
  open();
  expect(await screen.findByText("No images or videos yet.")).toBeTruthy();
});
