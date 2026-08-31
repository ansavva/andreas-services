import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { CharacterRecord } from "../../types";
import { TestProviders } from "../../test-providers";

vi.mock("../../apis/studio", () => ({
  draftTurnaround: vi.fn(),
  getProjects: vi.fn(),
  getReel: vi.fn(),
  getTree: vi.fn(),
  getAsset: vi.fn().mockResolvedValue({ url: "blob:x" }),
}));

import { draftTurnaround, getProjects, getReel, getTree } from "../../apis/studio";
import { TurnaroundPanel } from "./TurnaroundPanel";

const draft = vi.mocked(draftTurnaround);
const tree = vi.mocked(getTree);
const reel = vi.mocked(getReel);
const projects = vi.mocked(getProjects);

const RECORD = { id: "char-1", root: "node-root", slug: "subject-a" } as CharacterRecord;

function file(id: string, name: string) {
  return {
    id, name, key: `seed/${name}`, size: 10, last_modified: null,
    kind: "image" as const, content_type: "image/jpeg", url: `https://x/${id}`,
  };
}

function show() {
  return render(
    <TestProviders>
      <MemoryRouter>
        <TurnaroundPanel record={RECORD} />
      </MemoryRouter>
    </TestProviders>,
  );
}

function withSeedPool(files = [file("node-a", "a.jpg"), file("node-b", "b.jpg")]) {
  tree.mockResolvedValue({
    prefix: "", sort: "name", breadcrumbs: [],
    folders: [{ id: "node-seed", name: "seed" }],
    files: [], counts: { folders: 1, files: 0, media: 0 },
  } as never);
  reel.mockResolvedValue({ prefix: "", sort: "name", items: files, total: files.length } as never);
  projects.mockResolvedValue([{ id: "proj-1", slug: "refs" }] as never);
}

/**
 * The package's `Select` is an ARIA combobox button over a listbox, not a
 * native `<select>`, so it is opened and its option clicked. `fireEvent.change`
 * on it does nothing at all — the field stays empty, the button stays disabled,
 * and the failure then reads as "the button did not fire".
 */
async function chooseProject(label = "refs") {
  fireEvent.click(screen.getByRole("combobox", { name: /project/i }));
  fireEvent.click(await screen.findByRole("option", { name: label }));
}


afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("reads the seed pool RECURSIVELY, so filed photographs are pickable", async () => {
  /**
   * A seed pool is a tree the moment anyone files it — `original/`, `restored/`,
   * a folder per age — and a listing one level deep shows only what was never
   * filed. That exact blindness kept thirteen restored photographs out of a
   * shoot's view on the CLI side, silently.
   */
  withSeedPool();
  show();
  await waitFor(() => expect(reel).toHaveBeenCalled());
  expect(reel.mock.calls[0]![0]).toEqual({ node: "node-seed" });
});

it("will not shoot until a project and at least one photograph are chosen", async () => {
  withSeedPool();
  show();
  const button = (await screen.findByText("Draft the angles")) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  expect(screen.getByText(/Pick at least one photograph/)).toBeTruthy();
});

it("sends the picked nodes IN THE ORDER they were picked", async () => {
  /**
   * The model is handed them in this order, and a prompt citing `[Image2]` means
   * the second one. A set would lose that, and the citation would land on
   * whichever image the grid happened to sort first.
   */
  withSeedPool();
  draft.mockResolvedValue({ drafted: [], failed: [] });
  show();

  fireEvent.click(await screen.findByLabelText(/b\.jpg/));
  fireEvent.click(screen.getByLabelText(/a\.jpg/));
  await chooseProject();
  fireEvent.click(screen.getByText("Draft the angles"));

  await waitFor(() => expect(draft).toHaveBeenCalled());
  expect(draft.mock.calls[0]![1].identity).toEqual(["node-b", "node-a"]);
});

it("shows each pick's SLOT NUMBER rather than a tick", async () => {
  withSeedPool();
  show();
  fireEvent.click(await screen.findByLabelText(/b\.jpg/));
  // The label carries it too, so the number is not colour-only or shape-only.
  expect(screen.getByLabelText(/b\.jpg, picked 1/)).toBeTruthy();
});

it("previews without recording anything", async () => {
  withSeedPool();
  draft.mockResolvedValue({
    preview: [{ angle: "face_front", model: "m",
                plan: { prompt: "A studio portrait.", params: {} }, sends: [] }],
    failed: [],
  });
  show();

  fireEvent.click(await screen.findByLabelText(/a\.jpg/));
  await chooseProject();
  fireEvent.click(screen.getByText("Preview"));

  await waitFor(() => expect(draft).toHaveBeenCalled());
  expect(draft.mock.calls[0]![1].preview).toBe(true);
  expect(await screen.findByText("A studio portrait.")).toBeTruthy();
});

it("says plainly that a draft is neither approved nor paid for", async () => {
  /**
   * Hard rule #2 is untouched by this screen: it makes the payload, a person
   * still says yes to it on the run's own page. A button that read "Shoot"
   * with no such line would be teaching somebody that this is the yes.
   */
  withSeedPool();
  draft.mockResolvedValue({
    drafted: [{ angle: "face_front", id: "run-1", status: "draft" }],
    failed: [],
  });
  show();

  fireEvent.click(await screen.findByLabelText(/a\.jpg/));
  await chooseProject();
  expect(screen.getByText(/Nothing is approved and nothing bills/)).toBeTruthy();

  fireEvent.click(screen.getByText("Draft the angles"));
  expect(await screen.findByText(/Nothing is approved and nothing has been submitted/)).toBeTruthy();
  expect(screen.getByText("face_front").closest("a")).toBeTruthy();
});

it("reports the angles that failed without hiding the ones that worked", async () => {
  withSeedPool();
  draft.mockResolvedValue({
    drafted: [{ angle: "face_front", id: "run-1", status: "draft" }],
    failed: [{ angle: "face_back", error: "cites {no_such_block}" }],
  });
  show();

  fireEvent.click(await screen.findByLabelText(/a\.jpg/));
  await chooseProject();
  fireEvent.click(screen.getByText("Draft the angles"));

  expect(await screen.findByText(/1 angle\(s\) were not drafted/)).toBeTruthy();
  expect(screen.getByText(/no_such_block/)).toBeTruthy();
  expect(screen.getByText(/1 draft\(s\)/)).toBeTruthy();
});

it("says so when the character has no seed pool at all", async () => {
  tree.mockResolvedValue({
    prefix: "", sort: "name", breadcrumbs: [], folders: [], files: [],
    counts: { folders: 0, files: 0, media: 0 },
  } as never);
  projects.mockResolvedValue([] as never);
  show();
  expect(await screen.findByText(/no seed pool/i)).toBeTruthy();
  expect(reel).not.toHaveBeenCalled();
});
