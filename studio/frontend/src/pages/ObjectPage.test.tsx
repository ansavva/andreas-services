import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FileEntry, RunRecord, FolderListing } from "../types";
import { TestProviders } from "../test-providers";

/**
 * What the object screen walks through, and where it gets it.
 *
 * **This is the file the whole `?in=` rework rests on.** The viewer used to be
 * the folder browser with a file laid over it, so opening a run's output left
 * the run; now the address names the sequence and the page has to pick the
 * right source and find the open node inside it. Getting that wrong is silent —
 * the frame still renders, it is just surrounded by the wrong neighbours.
 *
 * These cases survived the reel unchanged, which is the point of asserting them
 * here: what Phase C replaced is the body, and the source selection, the
 * position within it and the address rewriting are none of it.
 */
vi.mock("../apis/studio", () => ({
  getFolder: vi.fn(),
  getRun: vi.fn(),
  getScene: vi.fn(),
  getNode: vi.fn(),
  getAsset: vi.fn(),
  getNodeOwner: vi.fn().mockResolvedValue(null),
  deleteNodes: vi.fn(),
  describeNode: vi.fn(),
  renameNode: vi.fn(),
}));

import { getAsset, getNode, getRun, getFolder } from "../apis/studio";
import { ObjectPage } from "./ObjectPage";

const tree = vi.mocked(getFolder);
const run = vi.mocked(getRun);
const node = vi.mocked(getNode);
const asset = vi.mocked(getAsset);

const FOLDER = "node-folder";
const OPEN = "node-b";

function file(id: string, name: string, over: Partial<FileEntry> = {}): FileEntry {
  return {
    id,
    key: name,
    name,
    size: 10,
    last_modified: "2026-08-20T00:00:00Z",
    kind: "image",
    content_type: "image/png",
    url: `https://example.invalid/${id}.png`,
    ...over,
  };
}

function listing(files: FileEntry[]): FolderListing {
  return {
    prefix: "",
    sort: "newest",
    depth: "1" as const,
    tags: {},
    breadcrumbs: [],
    folders: [],
    files,
  };
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  tree.mockResolvedValue(listing([file("node-a", "a.png"), file(OPEN, "b.png"), file("node-c", "c.png")]));
});

function open(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/o" element={<ObjectPage />} />
        <Route path="/o/:nodeId" element={<ObjectPage />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
}

describe("which sequence the address names", () => {
  it("walks a folder, and opens on the file that was clicked", async () => {
    open(`/o/${OPEN}?in=${encodeURIComponent(`f:${FOLDER}`)}`);

    // "2 of 3" is the whole assertion: the folder is the source, and the open
    // node's position in it is what the page opened on rather than the top.
    await waitFor(() => expect(screen.getByText(/2 of 3/)).toBeTruthy());
    // The third argument is the tag filter, empty here — a folder walk asks for
    // the folder, not for a search.
    expect(tree).toHaveBeenCalledWith({ node: FOLDER }, "newest", { tag: [] });
  });

  it("walks a RUN's frames, and never asks for a folder", async () => {
    // The bug this rework existed to kill: a run's output opened the file tree.
    run.mockResolvedValue({
      id: "run-1",
      outputs: [
        { node: "node-out", name: "out.png", url: "https://example.invalid/out.png", content_type: "image/png" },
      ],
      bindings: {},
    } as unknown as RunRecord);

    open(`/o/node-out?in=${encodeURIComponent("run:run-1")}`);

    await waitFor(() => expect(run).toHaveBeenCalledWith("run-1"));
    expect(tree).not.toHaveBeenCalled();
  });

  it("shows one file and asks for the node itself when there is no context", async () => {
    // A share link's usual shape. It must not guess a folder.
    node.mockResolvedValue({
      id: "node-lone",
      lib: "lib-1",
      name: "lone.png",
      kind: "file",
      content_type: "image/png",
      created_at: "2026-08-20T00:00:00Z",
    } as never);
    asset.mockResolvedValue({ url: "https://example.invalid/lone.png" } as never);

    open("/o/node-lone");

    await waitFor(() => expect(node).toHaveBeenCalledWith("node-lone"));
    expect(tree).not.toHaveBeenCalled();
    expect(run).not.toHaveBeenCalled();
  });

  it("opens a feed at its first frame when the address carries no id", async () => {
    // `/o?in=…` with no id. Nothing in the app builds one now that "Play reel"
    // is gone, but the viewer still opens on the first frame and the id appears
    // a moment later, so an old link does not dead-end.
    open(`/o?in=${encodeURIComponent(`f:${FOLDER}`)}`);

    await waitFor(() => expect(screen.getByText(/1 of 3/)).toBeTruthy());
  });
});

describe("editing the file's own fields", () => {
  /** Opens the folder feed on `OPEN` and presses the one editing control. */
  async function openEditor() {
    open(`/o/${OPEN}?in=${encodeURIComponent(`f:${FOLDER}`)}`);
    await waitFor(() => expect(screen.getByText(/2 of 3/)).toBeTruthy());

    // One control, and it is the same one in the header and over the player —
    // hence `getAllBy`. There used to be two here, a describe toggle and a
    // rename dialog, editing three fields of one row between them.
    fireEvent.click(screen.getAllByLabelText("Edit details")[0]!);
    return await screen.findByRole("dialog");
  }

  it("opens one drawer holding the name beside the description", async () => {
    const drawer = await openEditor();

    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("b.png");
    expect(screen.getByLabelText("Description")).toBeTruthy();
    expect(screen.getByLabelText("Add a tag")).toBeTruthy();
    // Nothing named "Rename" is left to open a second surface.
    expect(screen.queryByLabelText(/^Rename/)).toBeNull();
    // The read-only details stay on the page under it. The editor used to take
    // their place in the column, so opening it hid the thing being edited.
    expect(drawer.contains(screen.getByLabelText("File details"))).toBe(false);
  });

  it("refuses a dismissal while words are unsaved, and keeps them", async () => {
    await openEditor();

    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Shirtless at the pool." },
    });
    fireEvent.click(document.querySelector("[data-drawer-backdrop]")!);

    expect(screen.getByText("Leave without saving?")).toBeTruthy();
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect((screen.getByLabelText("Description") as HTMLTextAreaElement).value).toBe(
      "Shirtless at the pool.",
    );

    // And the way out is offered rather than taken.
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("takes a pristine dismissal at face value", async () => {
    const drawer = await openEditor();

    fireEvent.keyDown(drawer, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // Escape closed the drawer and NOT the page: two listeners answering one
    // press is a dismissal and a `navigate(-1)`, which is one key leaving two
    // screens.
    expect(screen.getByText(/2 of 3/)).toBeTruthy();
  });
});

describe("walking the feed", () => {
  it("steps with the arrow keys and rewrites the address", async () => {
    // The reel scrolled and reported the settled pane; a page steps. Both end
    // in the same `replace` navigation, which is what keeps twenty files looked
    // at from being twenty back-presses to escape.
    open(`/o/node-a?in=${encodeURIComponent(`f:${FOLDER}`)}`);
    await waitFor(() => expect(screen.getByText(/1 of 3/)).toBeTruthy());

    fireEvent.keyDown(window, { key: "ArrowRight" });
    await waitFor(() => expect(screen.getByText(/2 of 3/)).toBeTruthy());

    fireEvent.keyDown(window, { key: "ArrowLeft" });
    await waitFor(() => expect(screen.getByText(/1 of 3/)).toBeTruthy());
  });

  it("does not step past either end", async () => {
    open(`/o/node-a?in=${encodeURIComponent(`f:${FOLDER}`)}`);
    await waitFor(() => expect(screen.getByText(/1 of 3/)).toBeTruthy());

    fireEvent.keyDown(window, { key: "ArrowLeft" });
    await waitFor(() => expect(screen.getByText(/1 of 3/)).toBeTruthy());
  });
});
