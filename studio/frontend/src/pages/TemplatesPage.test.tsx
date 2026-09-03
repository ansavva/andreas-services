import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { TemplateLibrary } from "../types";
import { TestProviders } from "../test-providers";

vi.mock("../apis/studio", () => ({
  deleteBlock: vi.fn(),
  getTemplates: vi.fn(),
  saveBlock: vi.fn(),
  saveTemplate: vi.fn(),
  // The plate beside each template: a node view, then its presigned url.
  getAsset: vi.fn().mockResolvedValue({ url: "https://signed/plate.png" }),
}));

import {
  deleteBlock,
  getTemplates,
  saveBlock,
  saveTemplate,
} from "../apis/studio";
import { TemplatesPage } from "./TemplatesPage";

const read = vi.mocked(getTemplates);
const savedBlock = vi.mocked(saveBlock);
const removeBlock = vi.mocked(deleteBlock);

const SPEC: TemplateLibrary = {
  blocks: { face_only: "THE FACE COMES FROM THE REFERENCE IMAGES." },
  templates: [
    {
      id: "template-face-front",
      name: "Face, front",
      prompt: "A studio portrait, front on. {face_only} {top}",
      description: "Head and shoulders, front on.",
      tags: ["face", "front"],
    },
  ],
};

function show() {
  return render(
    <TestProviders>
      <MemoryRouter>
        <TemplatesPage />
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
   * They were inlined under each template for a while. The argument was that a
   * template is mostly citations, so a prompt read without its blocks is a
   * third of a prompt — and that argument is now answered by `PromptPreview`,
   * which writes every block out beside the box as you type. The inline copies
   * were the same prose a second time, pushing the next template off the screen.
   */
  read.mockResolvedValue(SPEC);
  show();
  // By NAME. The id is the row's key and the route's address — minted for a
  // create, never shown and never typed.
  expect(await screen.findByText(/Face, front/)).toBeTruthy();

  // The prose is on screen — expanded into the preview, not as an editor.
  expect(screen.getByLabelText("Assembled preview").textContent).toContain(
    "THE FACE COMES FROM THE REFERENCE IMAGES.",
  );
  expect(screen.queryByRole("button", { name: /\{face_only\}/ })).toBeNull();

  await blocksTab();
  expect(screen.getByRole("button", { name: /\{face_only\}/ })).toBeTruthy();
});

it("lists EVERY block, not only the ones some template happens to cite", async () => {
  /**
   * A block nothing cites is the one most likely to be wrong, and inlining
   * under citations made it the one thing the screen could not show.
   */
  read.mockResolvedValue({
    blocks: { ...SPEC.blocks, orphan: "Nothing cites this." },
    templates: SPEC.templates,
  });
  show();
  await blocksTab();
  expect(screen.getByRole("button", { name: /\{orphan\}/ })).toBeTruthy();
  expect(screen.getByText("0 templates")).toBeTruthy();
});

it("says how many templates a block reaches BEFORE it is edited", async () => {
  /**
   * A block reads as local until you know it is not, and a shared edit noticed
   * on save is noticed too late.
   */
  read.mockResolvedValue({
    blocks: SPEC.blocks,
    templates: [
      SPEC.templates[0]!,
      { ...SPEC.templates[0]!, name: "Face, back", prompt: "Back. {block.face_only}" },
    ],
  });
  show();
  await blocksTab();
  expect(screen.getByText("2 templates")).toBeTruthy();
});

it("says what to do when a library holds no templates at all", async () => {
  /**
   * A fresh stack has none, and a turnaround cannot run without templates. An
   * empty screen would read as a bug rather than as a step nobody has taken.
   */
  read.mockResolvedValue({ blocks: {}, templates: [] });
  show();
  expect(await screen.findByText(/No templates yet/i)).toBeTruthy();
  expect(screen.getByText(/templates push/)).toBeTruthy();
});

it("names a placeholder no block provides, while it is still being typed", async () => {
  /**
   * The failure this screen makes possible: deleting a block is one click, and
   * the template citing it does not break until somebody drafts. `{top}` is
   * computed by the assembler rather than read off a row, so it must NOT be
   * flagged — marking every computed value as unknown would make the warning
   * noise nobody reads.
   */
  read.mockResolvedValue({
    blocks: SPEC.blocks,
    templates: [
      {
        ...SPEC.templates[0]!,
        // `{face_only}` is the bare spelling and no longer resolves at all, so
        // it is flagged like any other unknown name — `{block.face_only}` is
        // the one that works.
        prompt: "{block.face_only} {character.1.top} {block.no_such_block}",
      },
    ],
  });
  show();

  // In WORDS. A Badge here is neutral chrome with an intent dot by design, so a
  // red-vs-grey pill would have carried the warning on hue alone.
  expect(await screen.findByText(/No block provides this name/i)).toBeTruthy();
  expect(screen.getByText(/no_such_block —/)).toBeTruthy();
  // `{character.1.top}` is computed from the bible rather than read off a row,
  // so flagging it would make the warning noise nobody reads.
  expect(screen.queryByText(/character\.1\.top —/)).toBeNull();
});

it("saves one block without refetching the whole spec", async () => {
  /**
   * A re-GET to show one paragraph somebody is still reading would replace
   * every editor on the page, including the ones with unsaved text in them.
   */
  read.mockResolvedValue(SPEC);
  savedBlock.mockResolvedValue({ name: "face_only", text: "edited" });
  show();

  await blocksTab();
  fireEvent.click(screen.getByRole("button", { name: /\{face_only\}/ }));
  const box = await screen.findByDisplayValue(/THE FACE COMES FROM/);
  fireEvent.change(box, { target: { value: "edited" } });
  fireEvent.click(screen.getAllByText("Save")[0]!);

  await waitFor(() => expect(savedBlock).toHaveBeenCalledWith("face_only", "edited"));
  expect(read).toHaveBeenCalledTimes(1);
});

it("does not offer to save until something has changed", async () => {
  read.mockResolvedValue(SPEC);
  show();
  const save = (await screen.findAllByText("Save"))[0] as HTMLButtonElement;
  expect(save.disabled).toBe(true);
});


it("creates a block, which is the same call as editing one", async () => {
  /**
   * `PATCH` on a name nothing holds creates it — the route is an overwrite
   * rather than a claim, because a block IS its name. So there is one route and
   * this is a form, not a second endpoint.
   */
  read.mockResolvedValue(SPEC);
  savedBlock.mockResolvedValue({ name: "backdrop_body", text: "White seamless." });
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
    expect(savedBlock).toHaveBeenCalledWith("backdrop_body", "White seamless."),
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

it("deletes a block, and says how many templates it will break first", async () => {
  /**
   * Nothing checks whether an template still cites it — a template names its
   * blocks in prose, so the only honest check is to assemble every template and
   * see what fails, which the assembly does loudly. What this screen can do is
   * say the count before the press, because it already knows it.
   */
  read.mockResolvedValue(SPEC);
  removeBlock.mockResolvedValue(undefined as never);
  show();
  await blocksTab();

  fireEvent.click(screen.getByRole("button", { name: /\{face_only\}/ }));
  // A cited block takes templates down with it, so it types its name rather
  // than arming in place — the gate a project or a character gets, not a file's.
  fireEvent.click(screen.getByRole("button", { name: "Delete" }));
  const dialog = await screen.findByRole("alertdialog");
  expect(dialog.textContent).toContain("1 template cites it");
  fireEvent.change(within(dialog).getByLabelText("Confirm"), {
    target: { value: "face_only" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

  await waitFor(() => expect(removeBlock).toHaveBeenCalledWith("face_only"));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: /\{face_only\}/ })).toBeNull(),
  );
});


it("renames a template by its ID, not by the name it had", async () => {
  /**
   * **The key does not move.** A rename used to write the new key and drop the
   * old, because the name WAS the key — so the row a run might one day point at
   * disappeared every time somebody fixed a typo. The name is a field now, and
   * this is the assertion that keeps it one: the address is the id, and the new
   * name rides in the body.
   */
  read.mockResolvedValue(SPEC);
  vi.mocked(saveTemplate).mockResolvedValue({
    ...SPEC.templates[0]!,
    name: "Face, straight on",
  });
  show();

  const box = await screen.findByDisplayValue("Face, front");
  fireEvent.change(box, { target: { value: "Face, straight on" } });
  fireEvent.click(screen.getAllByRole("button", { name: /^Save/ })[0]!);

  await waitFor(() =>
    expect(saveTemplate).toHaveBeenCalledWith(
      "template-face-front",
      expect.objectContaining({ name: "Face, straight on" }),
    ),
  );
});
