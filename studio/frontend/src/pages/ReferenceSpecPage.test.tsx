import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { ReferenceSpec } from "../types";
import { TestProviders } from "../test-providers";

vi.mock("../apis/studio", () => ({
  deleteSpecBlock: vi.fn(),
  getReferenceSpec: vi.fn(),
  saveSpecBlock: vi.fn(),
  saveSpecAngle: vi.fn(),
  // The plate beside each angle: a node view, then its presigned url.
  resolvePath: vi.fn().mockResolvedValue({ id: "node-plate", name: "front.png", kind: "file" }),
  getAsset: vi.fn().mockResolvedValue({ url: "https://signed/plate.png" }),
}));

import {
  deleteSpecBlock,
  getReferenceSpec,
  resolvePath,
  saveSpecBlock,
} from "../apis/studio";
import { ReferenceSpecPage } from "./ReferenceSpecPage";

const read = vi.mocked(getReferenceSpec);
const saveBlock = vi.mocked(saveSpecBlock);
const removeBlock = vi.mocked(deleteSpecBlock);

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
      illustration: "config/angle/face/front.png",
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

/** Open the Blocks tab, which is where a block's prose is edited. */
async function blocksTab() {
  fireEvent.click(await screen.findByRole("tab", { name: /Blocks/ }));
}

it("keeps the blocks on their OWN tab, and previews them beside the prompt", async () => {
  /**
   * They were inlined under each angle for a while. The argument was that a
   * template is mostly citations, so a prompt read without its blocks is a
   * third of a prompt — and that argument is now answered by `PromptPreview`,
   * which writes every block out beside the box as you type. The inline copies
   * were the same prose a second time, pushing the next angle off the screen.
   */
  read.mockResolvedValue(SPEC);
  show();
  expect(await screen.findByText(/face_front/)).toBeTruthy();

  // The prose is on screen — expanded into the preview, not as an editor.
  expect(screen.getByLabelText("Assembled preview").textContent).toContain(
    "THE FACE COMES FROM THE REFERENCE IMAGES.",
  );
  expect(screen.queryByRole("button", { name: /\{face_only\}/ })).toBeNull();

  await blocksTab();
  expect(screen.getByRole("button", { name: /\{face_only\}/ })).toBeTruthy();
});

it("lists EVERY block, not only the ones some angle happens to cite", async () => {
  /**
   * A block nothing cites is the one most likely to be wrong, and inlining
   * under citations made it the one thing the screen could not show.
   */
  read.mockResolvedValue({
    blocks: { ...SPEC.blocks, orphan: "Nothing cites this." },
    angles: SPEC.angles,
  });
  show();
  await blocksTab();
  expect(screen.getByRole("button", { name: /\{orphan\}/ })).toBeTruthy();
  expect(screen.getByText("0 angles")).toBeTruthy();
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
  await blocksTab();
  expect(screen.getByText("2 angles")).toBeTruthy();
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

  await blocksTab();
  fireEvent.click(screen.getByRole("button", { name: /\{face_only\}/ }));
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

it("shows the angle's PLATE, which is what the orientation means", async () => {
  /**
   * This screen is where an angle's words are written, and it showed the id and
   * nothing else — so what `face_three_quarter_back_right` actually means was
   * only visible on the tab you shoot from.
   */
  read.mockResolvedValue(SPEC);
  show();
  await screen.findByText(/face_front/);
  await waitFor(() => expect(resolvePath).toHaveBeenCalledWith("config/angle/face/front.png"));
});

it("creates a block, which is the same call as editing one", async () => {
  /**
   * `PATCH` on a name nothing holds creates it — the route is an overwrite
   * rather than a claim, because a block IS its name. So there is one route and
   * this is a form, not a second endpoint.
   */
  read.mockResolvedValue(SPEC);
  saveBlock.mockResolvedValue({ name: "backdrop_body", text: "White seamless." });
  show();
  await blocksTab();

  fireEvent.click(screen.getByText("+ New block"));
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "backdrop_body" },
  });
  fireEvent.change(screen.getByLabelText("Text"), {
    target: { value: "White seamless." },
  });
  fireEvent.click(screen.getByText("Create"));

  await waitFor(() =>
    expect(saveBlock).toHaveBeenCalledWith("backdrop_body", "White seamless."),
  );
  expect(await screen.findByRole("button", { name: /\{backdrop_body\}/ })).toBeTruthy();
});

it("refuses a name no template could ever cite", async () => {
  /**
   * A block is cited as `{block.<name>}` and a dot is attribute access, so a
   * name that is not an identifier is a block nothing can name. The API refuses
   * it; saying so here means finding out while typing.
   */
  read.mockResolvedValue(SPEC);
  show();
  await blocksTab();

  fireEvent.click(screen.getByText("+ New block"));
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "2fast" } });
  fireEvent.change(screen.getByLabelText("Text"), { target: { value: "prose" } });

  expect(screen.getByText(/Lowercase letters, digits and underscores/)).toBeTruthy();
  expect((screen.getByText("Create") as HTMLButtonElement).disabled).toBe(true);
});

it("will not silently overwrite a block that already exists", async () => {
  read.mockResolvedValue(SPEC);
  show();
  await blocksTab();

  fireEvent.click(screen.getByText("+ New block"));
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "face_only" } });
  expect(screen.getByText(/already holds that name/)).toBeTruthy();
});

it("deletes a block, and says how many angles it will break first", async () => {
  /**
   * Nothing checks whether an angle still cites it — a template names its
   * blocks in prose, so the only honest check is to assemble every angle and
   * see what fails, which the assembly does loudly. What this screen can do is
   * say the count before the press, because it already knows it.
   */
  read.mockResolvedValue(SPEC);
  removeBlock.mockResolvedValue(undefined as never);
  show();
  await blocksTab();

  fireEvent.click(screen.getByRole("button", { name: /\{face_only\}/ }));
  const arm = screen.getByRole("button", { name: /Delete/ });
  fireEvent.click(arm);
  expect(screen.getByText(/1 angle\(s\) cite it/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /1 angle\(s\) cite it/ }));

  await waitFor(() => expect(removeBlock).toHaveBeenCalledWith("face_only"));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: /\{face_only\}/ })).toBeNull(),
  );
});
