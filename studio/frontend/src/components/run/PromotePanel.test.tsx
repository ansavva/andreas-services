import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/studio", () => ({
  getCharacters: vi.fn(),
  getCharacter: vi.fn(),
  getFolder: vi.fn(),
  getTags: vi.fn().mockResolvedValue([]),
  copyNodes: vi.fn(),
  describeNode: vi.fn(),
}));

import { ApiError } from "../../apis/client";
import {
  describeNode,
  copyNodes,
  getCharacter,
  getCharacters,
  getFolder,
} from "../../apis/studio";
import { PromotePanel, copyIntoCharacter } from "./PromotePanel";
import { TestProviders } from "../../test-providers";
import type { CopiedNodes, NodeRecord, RunAsset, FolderListing } from "../../types";

/**
 * Copying a run's output into a character — **a real copy, then the tags.**
 *
 * What these pin is the order and the identity of what gets described.
 * Describing the ORIGINAL would put a run's own output into a character, which
 * is the one thing the copy exists to prevent: the run keeps its output, and
 * every record citing it stays correct, only because the two are different
 * blobs.
 *
 * **The `default` tag is nobody's default any more.** This flow used to write
 * it on every copy, which made one press mean both "keep this under the
 * character" and "this is who the character is". The second is hard rule #2b's
 * decision and is now a tag somebody types.
 *
 * Placeholder slugs only (hard rule #1). No character in this library is named
 * in this repository.
 */

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

const list = vi.mocked(getCharacters);
const read = vi.mocked(getCharacter);
const tree = vi.mocked(getFolder);
const copy = vi.mocked(copyNodes);
const describe_ = vi.mocked(describeNode);

const CHAR = "char-1";
const OUTPUT = "node-out";
const ROOT = "node-root";
const FOLDER = "node-ref";

const asset: RunAsset = {
  node: OUTPUT,
  name: "frame.webp",
  content_type: "image/webp",
  url: "https://example.invalid/frame.webp",
};

/** A `getFolder` answer: its own name path, and the folders under it. */
function listing(prefix: string, named: Record<string, string> = {}): FolderListing {
  return {
    prefix,
    sort: "name",
    depth: "1" as const,
    tags: {},
    breadcrumbs: [{ id: prefix === "characters/c1" ? ROOT : FOLDER, name: prefix, prefix }],
    folders: Object.entries(named).map(([name, id]) => ({
      id,
      kind: "folder" as const,
      prefix: `${prefix}/${name}`,
      name,
      last_modified: null,
    })),
    files: [],
  };
}

function node(id: string, name: string): NodeRecord {
  return { id, name, kind: "file", lib: "lib-1", created_at: "" };
}

/** What `POST /api/nodes/copy` answers with — whole records, never bare ids. */
function copied(id: string, name: string): CopiedNodes {
  return { destination: FOLDER, copied: 1, nodes: [node(id, name)] };
}

/** The store as the panel walks it: a root, one folder in it, a copy, a describe. */
function stubStore(over: { copyName?: string } = {}) {
  read.mockResolvedValue({ id: CHAR, root: ROOT } as never);
  tree.mockImplementation(async (where) =>
    where.node === ROOT
      ? listing("characters/c1", { reference: FOLDER })
      : listing("characters/c1/reference"),
  );
  copy.mockResolvedValue(copied("node-copy", over.copyName ?? "frame.webp"));
  describe_.mockResolvedValue({ id: "node-copy" } as never);
}

describe("copyIntoCharacter", () => {
  it("copies into the folder it was given, then describes the COPY", async () => {
    const order: string[] = [];
    copy.mockImplementation(async () => {
      order.push("copy");
      return copied("node-copy", "frame (2).webp");
    });
    describe_.mockImplementation(async () => {
      order.push("describe");
      return { id: "node-copy" } as never;
    });

    const result = await copyIntoCharacter({
      node: OUTPUT,
      folder: FOLDER,
      where: "A subject/reference",
      tags: ["face"],
    });

    expect(order).toEqual(["copy", "describe"]);
    // **No folder is ensured and none is guessed.** The destination is the id
    // the picker handed back; this used to create a `reference/` pool of its own.
    expect(copy).toHaveBeenCalledWith([OUTPUT], FOLDER);
    // **The COPY's id**, and the name the destination decided — `frame.webp`
    // was taken, so it landed as `frame (2).webp` and nothing here guessed it.
    expect(describe_).toHaveBeenCalledWith("node-copy", { tags: ["face"] });
    expect(result.copy).toEqual({ id: "node-copy", name: "frame (2).webp" });
  });

  it("writes no tag nobody asked for — `default` least of all", async () => {
    stubStore();

    await copyIntoCharacter({ node: OUTPUT, folder: FOLDER, where: "x", tags: ["face"] });

    const written = describe_.mock.calls[0]![1] as { tags: string[] };
    expect(written.tags).toEqual(["face"]);
    expect(written.tags).not.toContain("default");
  });

  it("describes nothing at all when there is nothing to say", async () => {
    stubStore();

    await copyIntoCharacter({ node: OUTPUT, folder: FOLDER, where: "x" });

    // A copy with no tags and no description is one request, not two: the write
    // would carry an empty tag list, which is a change nobody asked for.
    expect(copy).toHaveBeenCalled();
    expect(describe_).not.toHaveBeenCalled();
  });

  it("reports a describe failure as a copy that landed somewhere", async () => {
    stubStore();
    describe_.mockRejectedValue(new ApiError("that node is gone", 400));

    await expect(
      copyIntoCharacter({
        node: OUTPUT,
        folder: FOLDER,
        where: "A subject/reference",
        tags: ["face"],
      }),
    ).rejects.toMatchObject({
      name: "DescribeFailed",
      copy: { id: "node-copy" },
      where: "A subject/reference",
    });
  });
});

describe("the panel", () => {
  function open(runCharacters: string[] = [CHAR]) {
    render(
      <MemoryRouter>
        <PromotePanel
          asset={asset}
          runCharacters={runCharacters}
          onClose={() => {}}
        />
      </MemoryRouter>,
      { wrapper: TestProviders },
    );
  }

  beforeEach(() => {
    list.mockResolvedValue([
      {
        id: CHAR,
        name: "A subject",
        hero: null,
        counts: { default: 2, files: 4 },
        updated: "2026-08-20T00:00:00Z",
      },
    ]);
  });

  /** Walk the picker: open it, step into the folder, take it. */
  async function chooseFolder() {
    fireEvent.click(await screen.findByRole("button", { name: /Choose a folder/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: "reference" }));
    fireEvent.click(await within(dialog).findByRole("button", { name: /^Copy here/ }));
  }

  it("asks for a folder rather than a group, and will not copy without one", async () => {
    /**
     * **There is no "group" any more.** It was a tag with a special name
     * pretending to be a place; where a picture goes is a folder, and which it
     * is is a choice rather than a convention this app knows.
     */
    stubStore();
    open();

    // Four labelled fields and a button, and no prose around them.
    expect(await screen.findByText("Copy into A subject")).toBeTruthy();
    expect(screen.getByText("Folder")).toBeTruthy();
    expect(screen.queryByLabelText("Group")).toBeNull();

    const button = (await screen.findByRole("button", {
      name: "Copy",
    })) as HTMLButtonElement;
    // The character is preselected — the folder is not, and it is required.
    expect(button.disabled).toBe(true);
  });

  it("copies into the folder that was picked, with the tags that were typed", async () => {
    /**
     * A run records who it was of, and one of them is not a guess. Two would
     * be — a picture of two people belongs to whichever the person says — which
     * is why the preselect is exactly the sole case.
     */
    stubStore();
    open();

    await chooseFolder();
    fireEvent.click(await screen.findByRole("button", { name: "Copy" }));

    await waitFor(() => expect(copy).toHaveBeenCalledWith([OUTPUT], FOLDER));
    // Nothing typed, so nothing described.
    expect(describe_).not.toHaveBeenCalled();
    // Said from the character down, never as the id its root folder is named
    // after.
    expect(await screen.findByText(/Copied into A subject\/reference/)).toBeTruthy();
  });

  /**
   * The dismissal guard's other half — reporting that this form holds words.
   *
   * The caller passes an inline arrow, so its identity changes on every render.
   * With that identity in the effect's dependency list the effect re-ran each
   * time and fired its own cleanup, which reports `false`. The visible symptom
   * was not a wrong value anywhere: it was that clicking outside a filled form
   * appeared to do nothing, because the warning it raised was cleared one
   * render later. Nothing in the app can report that.
   */
  it("keeps reporting dirty across a re-render with a new callback identity", async () => {
    stubStore();
    const reports: boolean[] = [];
    const view = render(
      <MemoryRouter>
        <PromotePanel
          asset={asset}
          runCharacters={[CHAR]}
          onClose={() => {}}
          onDirtyChange={(dirty) => reports.push(dirty)}
        />
      </MemoryRouter>,
      { wrapper: TestProviders },
    );

    fireEvent.change(
      await screen.findByPlaceholderText("Optional — what the image shows"),
      { target: { value: "three-quarter angle" } },
    );
    await waitFor(() => expect(reports.at(-1)).toBe(true));

    // A fresh arrow, exactly as a parent re-render hands one down.
    view.rerender(
      <MemoryRouter>
        <PromotePanel
          asset={asset}
          runCharacters={[CHAR]}
          onClose={() => {}}
          onDirtyChange={(dirty) => reports.push(dirty)}
        />
      </MemoryRouter>,
    );

    expect(reports.at(-1)).toBe(true);
  });

  it("names where the copy landed when the describe fails", async () => {
    /**
     * Nothing is rolled back — the bytes are real, and a component deleting
     * media on its own initiative is worse than a file in the wrong state. So
     * the partial state is reported in the words a person would go looking
     * with, which is the same partial state the CLI tolerates.
     */
    stubStore();
    describe_.mockRejectedValue(new ApiError("the row would not write", 500));
    open();

    await chooseFolder();
    fireEvent.change(
      screen.getByPlaceholderText("Optional — what the image shows"),
      { target: { value: "a face" } },
    );
    fireEvent.click(await screen.findByRole("button", { name: "Copy" }));

    expect(
      await screen.findByText(/A subject\/reference as “frame.webp”/),
    ).toBeTruthy();
    expect(screen.getByText(/run's own copy is fine/)).toBeTruthy();
  });
});
