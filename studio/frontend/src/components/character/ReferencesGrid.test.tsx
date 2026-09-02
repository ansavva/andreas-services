import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FileEntry, ReferenceEntry, ReferenceIndex, FolderListing } from "../../types";

// Three seams: where the entries come from, where a move goes, and the folder
// listing behind the "not attached" section.
vi.mock("../../apis/studio", () => ({
  getReferences: vi.fn(),
  getFolder: vi.fn(),
  patchReference: vi.fn(),
}));

import { getReferences, getFolder, patchReference } from "../../apis/studio";
import { ReferencesGrid } from "./ReferencesGrid";
import { TestProviders } from "../../test-providers";

const references = vi.mocked(getReferences);
const tree = vi.mocked(getFolder);
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

function listing(over: Partial<FolderListing>): FolderListing {
  return {
    prefix: "",
    sort: "name",
    depth: "1" as const,
    tags: {},
    breadcrumbs: [],
    folders: [],
    files: [],
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

// A router, because a tile opens the viewer now rather than a sheet of its own.
function renderGrid() {
  return render(
    <MemoryRouter>
      <ReferencesGrid characterId={CHARACTER} rootId={ROOT} defaultSet={[]} rev={1} onSaved={() => {}} />
    </MemoryRouter>,
  { wrapper: TestProviders },
  );
}

/*
 * The reordering cases moved to `ReferenceFields.test.tsx`.
 *
 * They pin what a step up or down SENDS — the anchor arithmetic that a naive
 * index-minus-two gets wrong — and those controls now live in the viewer's
 * panel rather than in a sheet this grid opened. The drag on the tiles below is
 * still here and still tested by what it calls.
 */

describe("the cap readout", () => {
  /**
   * `ENGINE_CAPS` is Kling 7, Seedance 9, Nano Banana 14.
   *
   * **The index is built to match the set**, which it did not have to be until
   * the count started ignoring members that are not references. A set naming ids
   * no `REF#` row points at is the exact drift the grid now warns about — see
   * the describe block below — so a fixture carrying it silently would be
   * testing the warning rather than the cap.
   */
  function withDefaultSet(size: number) {
    const nodes = Array.from({ length: size }, (_, i) => `node-d${i}`);
    references.mockResolvedValue({
      groups: { face: nodes.map((node, index) => entry(node, (index + 1) * 1000)) },
      counts: { face: size },
    });
    return render(
      <MemoryRouter>
        <ReferencesGrid characterId={CHARACTER} rootId={ROOT} defaultSet={nodes} rev={1} onSaved={() => {}} />
      </MemoryRouter>,
    { wrapper: TestProviders },
    );
  }

  it("shows the binding cap only, while the set is legal", async () => {
    // Three badges for one number is what this replaced. Under the smallest cap
    // you are under all of them, so the smallest is the only one that can turn.
    withDefaultSet(5);
    await screen.findByTitle("node-d0.png");

    expect(screen.getByText("Kling 5/7")).toBeTruthy();
    expect(screen.queryByText(/Seedance/)).toBeNull();
    expect(screen.queryByText(/Nano Banana/)).toBeNull();
  });

  it("names every engine the set is too big for, and only those", async () => {
    withDefaultSet(10);
    await screen.findByTitle("node-d0.png");

    expect(screen.getByText("over Kling (7)")).toBeTruthy();
    expect(screen.getByText("over Seedance (9)")).toBeTruthy();
    // 10 still fits Nano Banana's 14, so it is not a warning.
    expect(screen.queryByText(/Nano Banana/)).toBeNull();
  });

  it("stops showing headroom once anything is exceeded", async () => {
    withDefaultSet(8);
    await screen.findByTitle("node-d0.png");

    expect(screen.getByText("over Kling (7)")).toBeTruthy();
    expect(screen.queryByText("Kling 8/7")).toBeNull();
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
                kind: "folder" as const,
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


describe("a default set that has gone stale", () => {
  /**
   * Found in production, not imagined: one character's set named seven nodes and
   * three of them were still references. The re-shot plates were attached under
   * new ids and the set was never re-pointed, so a default shoot sent three
   * images where somebody had chosen seven — and this screen said "7".
   */
  function withStaleDefaults() {
    references.mockResolvedValue({
      groups: { face: [entry("node-a", 1000, { tags: ["portrait"] })] },
      counts: { face: 1 },
    });
    return render(
      <MemoryRouter>
        <ReferencesGrid
          characterId={CHARACTER}
          rootId={ROOT}
          defaultSet={["node-a", "node-gone-1", "node-gone-2"]}
          rev={1}
          onSaved={() => {}}
        />
      </MemoryRouter>,
    { wrapper: TestProviders },
    );
  }

  it("counts only the members that are still references", async () => {
    withStaleDefaults();
    await screen.findByTitle("node-a.png");

    // One of three, not three.
    expect(screen.getByText("Kling 1/7")).toBeTruthy();
  });

  it("says how many went stale rather than quietly leaving them out", async () => {
    withStaleDefaults();
    await screen.findByTitle("node-a.png");

    expect(screen.getByText("2 no longer a reference")).toBeTruthy();
    expect(
      screen.getByText(/2 of 3 in the default set are not references any more/),
    ).toBeTruthy();
  });

  it("says nothing when a tag is doing the selecting", async () => {
    // The warning is about the default set, and a tag does not consult it.
    withStaleDefaults();
    await screen.findByTitle("node-a.png");
    fireEvent.click(screen.getByRole("button", { name: "portrait" }));

    expect(screen.queryByText("2 no longer a reference")).toBeNull();
  });
});
