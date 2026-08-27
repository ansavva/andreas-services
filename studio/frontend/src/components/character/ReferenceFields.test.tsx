import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ReferenceEntry, ReferenceIndex } from "../../types";

vi.mock("../../apis/studio", () => ({
  getReferences: vi.fn(),
  patchReference: vi.fn(),
  deleteReference: vi.fn(),
}));

import { getReferences, patchReference } from "../../apis/studio";
import { ReferenceFields } from "./ReferenceFields";
import { TestProviders } from "../../test-providers";

const references = vi.mocked(getReferences);
const patch = vi.mocked(patchReference);

const CHARACTER = "char-0001";

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

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  references.mockResolvedValue(INDEX);
  patch.mockResolvedValue(entry("node-b", 2000));
});

/** The panel as the viewer renders it: on whichever node is open. */
async function open(node: string) {
  render(<ReferenceFields characterId={CHARACTER} node={node} onChanged={() => {}} />, { wrapper: TestProviders });
  await screen.findByText("Reference");
}

/**
 * Reordering, on a pointer that has no drag.
 *
 * **These moved here from `ReferencesGrid` with the fields themselves.** They
 * were written when reordering stopped being drag-only — `draggable` and
 * `onDrop` are HTML5 drag events, which no touch browser fires, so regrouping
 * and reordering silently did nothing on a phone. The controls used to live in
 * a bottom sheet and now live in the viewer's panel; what they send is
 * unchanged, and that is the whole point of keeping the cases.
 */
describe("moving a reference without a drag", () => {
  it("steps down by landing after its next neighbour", async () => {
    await open("node-b");

    fireEvent.click(screen.getByRole("button", { name: /down/i }));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledWith(CHARACTER, "node-b", {
        group: "face",
        after: "node-c",
      });
    });
  });

  it("steps up by landing after the entry two above it", async () => {
    await open("node-c");

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
    await open("node-b");

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

    await open("node-a");
    expect(disabled(/up/i)).toBe(true);
    expect(disabled(/down/i)).toBe(false);

    cleanup();

    await open("node-c");
    expect(disabled(/down/i)).toBe(true);
    expect(disabled(/up/i)).toBe(false);
  });

  it("says where the entry sits, so the buttons mean something", async () => {
    await open("node-b");
    expect(screen.getByText("2 of 3")).toBeTruthy();
  });
});

/**
 * The viewer scrolls through every drawable node in the pool, and not all of
 * them are references — an image can sit in `reference/` with no `REF#` row
 * claiming it. The panel has nothing character-shaped to say about those.
 */
it("renders nothing for a node no reference row claims", async () => {
  const { container } = render(
    <ReferenceFields characterId={CHARACTER} node="node-loose" onChanged={() => {}} />,
  { wrapper: TestProviders },
  );
  await waitFor(() => expect(references).toHaveBeenCalled());
  expect(container.textContent).toBe("");
});
