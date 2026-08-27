import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FileEntry, RunRecord, TreeResponse } from "../types";
import { TestProviders } from "../test-providers";

/**
 * What the viewer scrolls through, and where it gets it.
 *
 * **This is the file the whole `?in=` rework rests on.** The viewer used to be
 * the folder browser with a file laid over it, so opening a run's output left
 * the run; now the address names the sequence and the page has to pick the
 * right source and find the open node inside it. Getting that wrong is silent —
 * the frame still renders, it is just surrounded by the wrong neighbours.
 */
vi.mock("../apis/studio", () => ({
  getTree: vi.fn(),
  getRun: vi.fn(),
  getScene: vi.fn(),
  getReferences: vi.fn(),
  getNode: vi.fn(),
  getAsset: vi.fn(),
  getNodeOwner: vi.fn().mockResolvedValue(null),
  deleteNodes: vi.fn(),
  describeNode: vi.fn(),
  renameNode: vi.fn(),
}));

import { getAsset, getNode, getRun, getTree } from "../apis/studio";
import { ViewerPage } from "./ViewerPage";

const tree = vi.mocked(getTree);
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

function listing(files: FileEntry[]): TreeResponse {
  return {
    prefix: "",
    sort: "newest",
    breadcrumbs: [],
    folders: [],
    files,
    counts: { folders: 0, files: files.length, media: files.length },
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
        <Route path="/o" element={<ViewerPage />} />
        <Route path="/o/:nodeId" element={<ViewerPage />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
}

describe("which sequence the address names", () => {
  it("scrolls a folder, and opens on the file that was clicked", async () => {
    open(`/o/${OPEN}?in=${encodeURIComponent(`f:${FOLDER}`)}`);

    // "2 of 3" is the whole assertion: the folder is the source, and the open
    // node's position in it is what the viewer started on rather than the top.
    await waitFor(() => expect(screen.getByText(/2 of 3/)).toBeTruthy());
    expect(tree).toHaveBeenCalledWith({ node: FOLDER }, "newest");
  });

  it("scrolls a RUN's frames, and never asks for a folder", async () => {
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

  it("shows one pane and asks for the node itself when there is no context", async () => {
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
    // `/o?in=…` is what "Play reel" navigates to — see `feedPath`. The id
    // appears a moment later, when the first pane settles.
    open(`/o?in=${encodeURIComponent(`f:${FOLDER}`)}`);

    await waitFor(() => expect(screen.getByText(/1 of 3/)).toBeTruthy());
  });
});
