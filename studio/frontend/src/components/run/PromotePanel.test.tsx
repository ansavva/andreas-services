import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/studio", () => ({
  getCharacters: vi.fn(),
  getCharacter: vi.fn(),
  listNodes: vi.fn(),
  getFolder: vi.fn(),
  createNode: vi.fn(),
  copyNodes: vi.fn(),
  describeNode: vi.fn(),
}));

import { ApiError } from "../../apis/client";
import {
  describeNode,
  copyNodes,
  createNode,
  getCharacter,
  getCharacters,
  listNodes,
  getFolder,
} from "../../apis/studio";
import { PromotePanel, promoteToReference } from "./PromotePanel";
import { TestProviders } from "../../test-providers";
import type {
  CopiedNodes,
  NodeRecord,
  RunAsset,
  FolderListing,
} from "../../types";

/**
 * Promote to reference — **a real copy, then attach the COPY.**
 *
 * What these pin is the order and the identity of what gets the `REF#` row.
 * Attaching the ORIGINAL would make the run's own output the character's
 * identity, which is the one thing the copy exists to prevent: the run keeps its
 * output, and every record citing it stays correct, only because the two are
 * different blobs.
 *
 * Placeholder slugs only (hard rule #1). No character in this library is named
 * in this repository.
 */

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

const list = vi.mocked(getCharacters);
const read = vi.mocked(getCharacter);
const references = vi.mocked(listNodes);
const tree = vi.mocked(getFolder);
const create = vi.mocked(createNode);
const copy = vi.mocked(copyNodes);
const attach = vi.mocked(describeNode);

const CHAR = "char-1";
const OUTPUT = "node-out";

const asset: RunAsset = {
  node: OUTPUT,
  name: "frame.webp",
  content_type: "image/webp",
  url: "https://example.invalid/frame.webp",
};

/** A `getFolder` answer holding the folders named. */
function folders(named: Record<string, string>): FolderListing {
  return {
    prefix: "",
    sort: "name",
    depth: "1" as const,
    tags: {},
    breadcrumbs: [],
    folders: Object.entries(named).map(([name, id]) => ({
      id,
      kind: "folder" as const,
      prefix: name,
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
  return { destination: "node-group", copied: 1, nodes: [node(id, name)] };
}

/** The happy path's stubs: both folders already there, one copy, one attach. */
function stubStore(over: { copyName?: string } = {}) {
  read.mockResolvedValue({ id: CHAR, root: "node-root" } as never);
  tree.mockImplementation(async () => folders({ reference: "node-ref" }));
  references.mockResolvedValue({ tags: { face: 2 } } as never);
  copy.mockResolvedValue(copied("node-copy", over.copyName ?? "frame.webp"));
  attach.mockResolvedValue({ id: "node-copy" } as never);
}

describe("promoteToReference", () => {
  it("ensures the pool, copies, then TAGS the copy — in that order", async () => {
    const order: string[] = [];
    read.mockImplementation(async () => {
      order.push("character");
      return { id: CHAR, root: "node-root" } as never;
    });
    tree.mockImplementation(async (where) => {
      order.push(`list ${where.node}`);
      return folders({ reference: "node-ref" });
    });
    copy.mockImplementation(async () => {
      order.push("copy");
      return copied("node-copy", "frame (2).webp");
    });
    attach.mockImplementation(async () => {
      order.push("tag");
      return { id: "node-copy" } as never;
    });

    const result = await promoteToReference({
      character: CHAR,
      node: OUTPUT,
      group: "unsorted",
    });

    // **One folder, not two.** The group was a `<group>/` subfolder AND a column
    // on the row; it is a tag, so the copy lands in `reference/` and the group
    // is said once.
    expect(order).toEqual(["character", "list node-root", "copy", "tag"]);
    expect(copy).toHaveBeenCalledWith([OUTPUT], "node-ref");
    // **The COPY's id**, and the name the destination decided — `frame.webp`
    // was taken, so it landed as `frame (2).webp` and nothing here guessed it.
    expect(attach).toHaveBeenCalledWith(
      "node-copy",
      expect.objectContaining({ tags: ["default", "unsorted"] }),
    );
    expect(attach).not.toHaveBeenCalledWith(
      CHAR,
      expect.objectContaining({ node: OUTPUT }),
    );
    expect(result.copy).toEqual({ id: "node-copy", name: "frame (2).webp" });
  });

  it("takes the existing folder when the create loses a race", async () => {
    /**
     * `store.ensure_child_folder`'s shape: a 409 means something else created it
     * between the listing and the create, and the node it made is the right
     * answer. Idempotent by construction rather than by retrying.
     */
    read.mockResolvedValue({ id: CHAR, root: "node-root" } as never);
    let listed = 0;
    tree.mockImplementation(async () => {
      listed += 1;
      // Absent on the first look, there on the re-list after the conflict.
      // **`reference/` is the only folder ensured now** — the `<group>/` one is
      // gone, because the group is a tag rather than a place.
      return listed === 1 ? folders({}) : folders({ reference: "node-raced" });
    });
    create.mockRejectedValue(new ApiError("name already taken", 409, "conflict"));
    references.mockResolvedValue({ tags: {} } as never);
    copy.mockResolvedValue({
      ...copied("node-copy", "frame.webp"),
      destination: "node-raced",
    });
    attach.mockResolvedValue({ id: "node-copy" } as never);

    await promoteToReference({ character: CHAR, node: OUTPUT, group: "unsorted" });

    expect(copy).toHaveBeenCalledWith([OUTPUT], "node-raced");
  });

  it("reports an attach failure as a copy that landed somewhere", async () => {
    stubStore();
    attach.mockRejectedValue(new ApiError("that node is gone", 400));

    await expect(
      promoteToReference({ character: CHAR, node: OUTPUT, group: "face" }),
    ).rejects.toMatchObject({
      name: "AttachFailed",
      copy: { id: "node-copy" },
      group: "face",
    });
  });

  it("re-tagging is not a conflict, so there is no `already` branch to take", async () => {
    // Attaching a node twice was a 409 — the row either existed or did not.
    // Writing a tag onto a file that already carries it is the same write, so a
    // second promotion of the same picture is quietly correct rather than a
    // state this has to report.
    stubStore();

    const result = await promoteToReference({
      character: CHAR,
      node: OUTPUT,
      group: "unsorted",
    });

    expect(result.already).toBe(false);
    expect(attach).toHaveBeenCalledWith(
      "node-copy",
      expect.objectContaining({ tags: ["default", "unsorted"] }),
    );
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
        slug: "a-subject",
        display_name: "A subject",
        hero: null,
        counts: { default: 2, files: 4 },
        updated: "2026-08-20T00:00:00Z",
      },
    ]);
    references.mockResolvedValue({
      groups: {},
      counts: { face: 2 },
    } as never);
  });

  it("defaults the group to unsorted and says what pressing will do", async () => {
    /**
     * The CLI's default — `refs.py`'s `UNSORTED` — spelled the same way.
     *
     * The sentence is asserted for its MEANING rather than its mechanism. It
     * used to describe a copy into a `reference/<group>/` folder and "marks the
     * copy as identity", which is what the code does; what the reader is
     * deciding is whether later shots should look like this picture, and that
     * is what has to be on screen before they press.
     */
    open();

    expect(
      await screen.findByText(/References are the pictures studio works from/i),
    ).toBeTruthy();
    expect(
      (screen.getByLabelText("Group") as HTMLInputElement).placeholder,
    ).toBe("unsorted");
  });

  /** The button is disabled until the character list has landed and one is picked. */
  async function armed() {
    const button = (await screen.findByRole("button", {
      name: "Add reference",
    })) as HTMLButtonElement;
    await waitFor(() => expect(button.disabled).toBe(false));
    return button;
  }

  it("promotes into the run's sole character without being asked which", async () => {
    /**
     * A run records who it was of, and one of them is not a guess. Two would
     * be — an image of two people is a reference of whichever the person says —
     * which is why the preselect is exactly the sole case.
     */
    stubStore();
    open();

    fireEvent.click(await armed());

    await waitFor(() =>
      expect(attach).toHaveBeenCalledWith(
        "node-copy",
        expect.objectContaining({ tags: ["default", "unsorted"] }),
      ),
    );
    expect(await screen.findByText(/Added to .*'s references/)).toBeTruthy();
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

  it("names where the copy landed when the attach fails", async () => {
    /**
     * Nothing is rolled back — the bytes are real, and a component deleting
     * media on its own initiative is worse than a file in the wrong state. So
     * the partial state is reported in the words a person would go looking with,
     * which is the same partial state the CLI tolerates.
     */
    stubStore();
    attach.mockRejectedValue(new ApiError("the row would not write", 500));
    open();

    fireEvent.click(await armed());

    // The one message that still names a folder: the copy is really there and
    // the reader has to go and find it.
    expect(
      await screen.findByText(/“frame.webp”.*reference\/unsorted\/ folder/),
    ).toBeTruthy();
    expect(screen.getByText(/run's own copy is fine/)).toBeTruthy();
  });
});
