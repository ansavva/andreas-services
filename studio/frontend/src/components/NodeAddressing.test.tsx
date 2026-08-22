import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FileEntry } from "../types";

/**
 * The three call sites that ask the API for one file's bytes or text.
 *
 * **Every one of them takes a `string`, and the wrong string typechecks.** A row
 * carries both `id` and `key`; these want the id, and passing `key` instead
 * compiles, renders, and fails only against material uploaded through the app —
 * whose bytes live under an entity-prefixed key that the name path does not
 * resemble (#432). `apis/studio.test.ts` pins the *parameter*; this pins the
 * *argument*, which is the half a type cannot.
 */
vi.mock("../apis/studio", () => ({
  getAsset: vi.fn().mockResolvedValue({ url: "https://signed.example/fresh" }),
  getNodeText: vi.fn().mockResolvedValue({
    content: "# hello\n",
    language: "markdown",
    truncated: false,
    id: "node-0042",
    name: "notes.md",
  }),
  saveNodeText: vi.fn(),
}));

import { getAsset, getNodeText } from "../apis/studio";
import { MediaTile } from "./browse/MediaTile";
import { MediaSurface } from "./viewer/MediaSurface";
import { TextPage } from "./text/TextPage";
import { ViewerChrome } from "./viewer/ViewerChrome";

const signed = vi.mocked(getAsset);
const fetched = vi.mocked(getNodeText);

// The two strings differ in every case here on purpose. A fixture whose `id`
// and `key` looked alike would let the swap this file exists for pass.
const FILE: FileEntry = {
  id: "node-0042",
  key: "characters/subject-a/notes.md",
  name: "notes.md",
  size: 9,
  last_modified: "2026-08-19T12:00:00.000000+00:00",
  kind: "image",
  content_type: "image/webp",
  url: "https://signed.example/stale",
  language: "markdown",
};

// Testing Library registers its cleanup with Vitest globals on; they are off
// here, so an unmounted tree would stay in the document.
let restoreLocation: (() => void) | null = null;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  restoreLocation?.();
  restoreLocation = null;
});

describe("re-signing a tile whose URL expired", () => {
  it("asks by node id, not by name path", async () => {
    render(
      <MediaTile
        file={FILE}
        selected={false}
        selectionActive={false}
        onOpen={() => {}}
        onToggleSelect={() => {}}
      />,
    );

    // The element reports its own failure; that is the whole re-sign trigger.
    fireEvent.error(screen.getByRole("img"));

    await waitFor(() => expect(signed).toHaveBeenCalledWith(FILE.id));
  });

  it("asks the same way from the viewer as from the grid", async () => {
    // Two components, one hook, two call sites — and only one of them was
    // covered until a control showed the other could be swapped silently.
    render(<MediaSurface file={FILE} />);

    fireEvent.error(screen.getByRole("img"));

    await waitFor(() => expect(signed).toHaveBeenCalledWith(FILE.id));
  });
});

describe("the download button", () => {
  it("asks by node id, and asks for an attachment", async () => {
    // The handler navigates to the signed URL, which jsdom refuses to do and
    // reports as an unhandled "Not implemented". `assign` is non-configurable
    // on jsdom's Location, so the whole object is replaced rather than spied on.
    const location = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { assign: vi.fn() },
    });
    restoreLocation = () =>
      Object.defineProperty(window, "location", { configurable: true, value: location });

    // `attachment` is the only reason a cross-origin download downloads, so it
    // is asserted beside the address rather than in a case of its own.
    render(
      <ViewerChrome
        file={FILE}
        isFullscreen={false}
        fullscreenSupported={false}
        onToggleFullscreen={() => {}}
        onClose={() => {}}
      />,
    );

    fireEvent.click(screen.getByLabelText("Download"));

    await waitFor(() => expect(signed).toHaveBeenCalledWith(FILE.id, "attachment"));
  });
});

describe("opening a text file", () => {
  it("reads by node id, and still shows the name path", async () => {
    render(<TextPage file={FILE} onClose={() => {}} />);

    await waitFor(() => expect(fetched).toHaveBeenCalledWith(FILE.id));
    // The path is what a person copies into a `studio` command. Nothing
    // addresses a write with it any more, and it must still be on the screen.
    expect(screen.getByText(FILE.key)).toBeDefined();
  });
});
