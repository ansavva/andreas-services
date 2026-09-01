import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { ReferenceSpec } from "../types";
import { TestProviders } from "../test-providers";

vi.mock("../apis/studio", () => ({
  getReferenceSpec: vi.fn(),
  saveSpecBlock: vi.fn(),
  saveSpecAngle: vi.fn(),
}));

import { getReferenceSpec, saveSpecBlock } from "../apis/studio";
import { ReferenceSpecPage } from "./ReferenceSpecPage";

const read = vi.mocked(getReferenceSpec);
const saveBlock = vi.mocked(saveSpecBlock);

const SPEC: ReferenceSpec = {
  blocks: { face_only: "THE FACE COMES FROM THE REFERENCE IMAGES." },
  angles: [
    {
      id: "face_front",
      group: "face",
      prompt: "A studio portrait, front on. {face_only} {top}",
      description: "Head and shoulders, front on.",
      tags: ["face", "front"],
      order: 1000,
    },
  ],
};

function show() {
  return render(
    <TestProviders>
      <MemoryRouter>
        <ReferenceSpecPage />
      </MemoryRouter>
    </TestProviders>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("shows a block INSIDE the angle that cites it, not on another tab", async () => {
  /**
   * They were two tabs, which made the commonest edit — read a prompt, notice a
   * phrase is wrong, fix it — a switch, a hunt and a switch back, with the
   * prompt off screen while you changed the words it uses. A template is mostly
   * citations, so hiding the blocks hid most of the prompt.
   */
  read.mockResolvedValue(SPEC);
  show();
  expect(await screen.findByText(/face_front/)).toBeTruthy();
  // By ROLE: `{face_only}` now appears twice on purpose — once as a pill inside
  // the prompt, once as the block's own header. The header is the button.
  expect(screen.getByRole("button", { name: /\{face_only\}/ })).toBeTruthy();
  expect(screen.queryByRole("tab")).toBeNull();
});

it("says how many angles a block reaches BEFORE it is edited", async () => {
  /**
   * A block reads as local until you know it is not, and a shared edit noticed
   * on save is noticed too late.
   */
  read.mockResolvedValue({
    blocks: SPEC.blocks,
    angles: [
      SPEC.angles[0]!,
      { ...SPEC.angles[0]!, id: "face_back", prompt: "Back. {face_only}" },
    ],
  });
  show();
  const counts = await screen.findAllByText("2 angles");
  expect(counts.length).toBe(2);
});

it("says what to do when a library holds no spec at all", async () => {
  /**
   * A fresh stack has none, and a turnaround cannot run without angles. An
   * empty screen would read as a bug rather than as a step nobody has taken.
   */
  read.mockResolvedValue({ blocks: {}, angles: [] });
  show();
  expect(await screen.findByText(/holds no reference spec/i)).toBeTruthy();
  expect(screen.getByText(/spec push/)).toBeTruthy();
});

it("names a placeholder no block provides, while it is still being typed", async () => {
  /**
   * The failure this screen makes possible: deleting a block is one click, and
   * the angle citing it does not break until somebody drafts. `{top}` is
   * computed by the assembler rather than read off a row, so it must NOT be
   * flagged — marking every computed value as unknown would make the warning
   * noise nobody reads.
   */
  read.mockResolvedValue({
    blocks: SPEC.blocks,
    angles: [{ ...SPEC.angles[0]!, prompt: "{face_only} {top} {no_such_block}" }],
  });
  show();

  // In WORDS. A Badge here is neutral chrome with an intent dot by design, so a
  // red-vs-grey pill would have carried the warning on hue alone.
  expect(await screen.findByText(/No block provides this name/i)).toBeTruthy();
  expect(screen.getByText(/no_such_block —/)).toBeTruthy();
  // `{top}` is computed by the assembler, not read off a row: flagging it would
  // make the warning noise nobody reads.
  expect(screen.queryByText(/top —/)).toBeNull();
});

it("saves one block without refetching the whole spec", async () => {
  /**
   * A re-GET to show one paragraph somebody is still reading would replace
   * every editor on the page, including the ones with unsaved text in them.
   */
  read.mockResolvedValue(SPEC);
  saveBlock.mockResolvedValue({ name: "face_only", text: "edited" });
  show();

  // Expand the block where it sits, inside the angle that cites it.
  fireEvent.click(await screen.findByRole("button", { name: /\{face_only\}/ }));
  const box = await screen.findByDisplayValue(/THE FACE COMES FROM/);
  fireEvent.change(box, { target: { value: "edited" } });
  fireEvent.click(screen.getAllByText("Save")[0]!);

  await waitFor(() => expect(saveBlock).toHaveBeenCalledWith("face_only", "edited"));
  expect(read).toHaveBeenCalledTimes(1);
});

it("does not offer to save until something has changed", async () => {
  read.mockResolvedValue(SPEC);
  show();
  const save = (await screen.findAllByText("Save"))[0] as HTMLButtonElement;
  expect(save.disabled).toBe(true);
});
