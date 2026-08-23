import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FileEntry, ReferenceEntry, ReferenceIndex, TreeResponse } from "../../types";

// Three seams: where the entries come from, where a move goes, and the folder
// listing behind the "not attached" section.
vi.mock("../../apis/studio", () => ({
  getReferences: vi.fn(),
  getTree: vi.fn(),
  patchReference: vi.fn(),
}));

import { getReferences, getTree, patchReference } from "../../apis/studio";
import { ReferencesGrid } from "./ReferencesGrid";

const references = vi.mocked(getReferences);
const tree = vi.mocked(getTree);
const patch = vi.mocked(patchReference);

const CHARACTER = "char-0001";
const ROOT = "node-root";

function entry(node: string, order: number, extra: Partial<ReferenceEntry> = {}): ReferenceEntry {
  return {
    node,
    order,
    description: "",
    tags: [],
    file: { name: `${node}.png`, url: `https://example.invalid/${node}.png` },
    ...extra,
  };
}

/** Three in one group, so there is a middle entry with a neighbour either side. */
const INDEX: ReferenceIndex = {
  groups: { face: [entry("node-a", 1000), entry("node-b", 2000), entry("node-c", 3000)] },
  counts: { face: 3 },
};

function file(id: string, name: string): FileEntry {
  return {
    id,
    key: `<name>/reference/${name}`,
    name,
    size: 1,
    last_modified: null,
    kind: "image",
    content_type: "image/png",
    url: `https://example.invalid/${id}.png`,
  };
}

function listing(over: Partial<TreeResponse>): TreeResponse {
  return {
    prefix: "",
    sort: "name",
    breadcrumbs: [],
    folders: [],
    files: [],
    counts: { folders: 0, files: 0, media: 0 },
    ...over,
  };
}

// Testing Library only registers its own cleanup with Vitest globals on, and
// they are off here — the drawer portals into `document.body` and would survive
// into the next case.
afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  references.mockResolvedValue(INDEX);
  patch.mockResolvedValue(entry("node-b", 2000));
  // No `reference/` folder unless a case says otherwise.
  tree.mockResolvedValue(listing({}));
});

function renderGrid() {
  return render(<ReferencesGrid characterId={CHARACTER} rootId={ROOT} defaultSet={[]} />);
}

/** Open the sheet on one entry the way a finger does — a tap on its tile. */
async function openSheet(node: string) {
  renderGrid();
  const tile = await screen.findByTitle(`${node}.png`);
  fireEvent.click(tile);
  await screen.findByRole("dialog");
}

describe("moving a reference without a drag", () => {
  it("steps down by landing after its next neighbour", async () => {
    await openSheet("node-b");

    fireEvent.click(screen.getByRole("button", { name: /down/i }));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledWith(CHARACTER, "node-b", {
        group: "face",
        after: "node-c",
      });
    });
  });

  it("steps up by landing after the entry two above it", async () => {
    await openSheet("node-c");

    fireEvent.click(screen.getByRole("button", { name: /up/i }));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledWith(CHARACTER, "node-c", {
        group: "face",
        after: "node-a",
      });
    });
  });

  it("steps the second entry up to the top of the group, which sends no anchor", async () => {
    // There is no entry two above the second one, and `after: null` is what the
    // API reads as "the midpoint below the first" — so the key is absent, not
    // null. This is the case a naive index-minus-two gets wrong.
    await openSheet("node-b");

    fireEvent.click(screen.getByRole("button", { name: /up/i }));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledWith(CHARACTER, "node-b", { group: "face" });
    });
  });

  it("cannot step the ends off either end", async () => {
    // `toBeDisabled` is jest-dom's, which this suite does not install — the
    // property is on the element itself.
    const disabled = (name: RegExp) =>
      (screen.getByRole("button", { name }) as HTMLButtonElement).disabled;

    await openSheet("node-a");
    expect(disabled(/up/i)).toBe(true);
    expect(disabled(/down/i)).toBe(false);

    cleanup();

    await openSheet("node-c");
    expect(disabled(/down/i)).toBe(true);
    expect(disabled(/up/i)).toBe(false);
  });

  it("says where the entry sits, so the buttons mean something", async () => {
    await openSheet("node-b");
    expect(screen.getByText("2 of 3")).toBeTruthy();
  });
});

describe("the images in reference/ that no row claims", () => {
  /** Root holds `reference/`; that folder holds one attached image and one loose. */
  function withReferenceFolder(files: FileEntry[]) {
    tree.mockImplementation((where) => {
      const node = (where as { node?: string }).node;
      if (node === ROOT) {
        return Promise.resolve(
          listing({
            folders: [
              {
                id: "node-ref",
                name: "reference",
                prefix: "<name>/reference",
                last_modified: null,
              },
            ],
          }),
        );
      }
      return Promise.resolve(listing({ files }));
    });
  }

  it("names the ones with no reference row", async () => {
    withReferenceFolder([file("node-a", "attached.png"), file("node-loose", "loose.png")]);

    renderGrid();

    // The attached one is a reference and is not reported as loose; the other is.
    expect(await screen.findByText(/not attached/i)).toBeTruthy();
    expect(await screen.findByTitle("loose.png")).toBeTruthy();
    expect(screen.queryByTitle("attached.png")).toBeNull();
  });

  it("says nothing at all when every image in the folder is attached", async () => {
    withReferenceFolder([file("node-a", "a.png"), file("node-b", "b.png")]);

    renderGrid();

    await screen.findByTitle("node-a.png");
    expect(screen.queryByText(/not attached/i)).toBeNull();
  });

  it("says nothing when there is no reference folder, which is an ordinary state", async () => {
    // `reference/` is a convention the entity model stopped enforcing — a
    // character without one has no unattached pool to report, not an error.
    renderGrid();

    await screen.findByTitle("node-a.png");
    expect(screen.queryByText(/not attached/i)).toBeNull();
  });
});
